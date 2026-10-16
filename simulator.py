"""gbn and sr over a small, event-driven satellite channel."""

import argparse
from dataclasses import dataclass, asdict
import heapq
import json
from pathlib import Path
import random
import struct


def checksum(data):
    # add 16-bit words, carry the overflow around, then invert the result.
    if len(data) % 2:
        data += b'\x00'
    total = sum(struct.unpack('!' + 'H' * (len(data) // 2), data))
    while total >> 16:
        total = (total & 0xffff) + (total >> 16)
    return (~total) & 0xffff


def make_frame(kind, seq, payload=b''):
    body = struct.pack('!BI', kind, seq) + payload
    return struct.pack('!H', checksum(body)) + body


def read_frame(frame):
    if len(frame) < 7 or checksum(frame) != 0:
        return None
    kind, seq = struct.unpack('!BI', frame[2:7])
    return kind, seq, frame[7:]


@dataclass
class Config:
    protocol: str = 'sr'
    packets: int = 200
    window: int = 4
    bits: int = 3
    loss: float = 0.0
    corruption: float = 0.0
    delay: float = 0.0
    timeout: float = 1.0
    seed: int = 0
    extra_delay: float = 0.35
    rate: float = 2_000_000
    rtt: float = 0.5
    max_events: int = 2_000_000

    def validate(self):
        if self.protocol not in ('gbn', 'sr'):
            raise ValueError('protocol must be gbn or sr')
        if not 1 <= self.bits <= 20:
            raise ValueError('bits must be between 1 and 20')
        limit = 2 ** self.bits - 1 if self.protocol == 'gbn' else 2 ** (self.bits - 1)
        if not 1 <= self.window <= limit:
            raise ValueError(f'{self.protocol}: window must be between 1 and {limit}')
        if self.packets < 1 or self.packets > 2 ** 32:
            raise ValueError('packets must be between 1 and 2^32')
        for name in ('loss', 'corruption', 'delay'):
            if not 0 <= getattr(self, name) <= 1:
                raise ValueError(f'{name} must be in [0, 1]')
        if (self.timeout <= 0 or self.rate <= 0 or self.rtt < 0
                or self.extra_delay < 0 or self.max_events < 1):
            raise ValueError('invalid timeout, link timing, or event limit')


class Simulator:
    def __init__(self, config, log=None, forced_losses=None):
        config.validate()
        self.c = config
        self.m = 2 ** config.bits
        self.rng = random.Random(config.seed)
        self.log_output = log
        self.events = []
        self.event_id = 0
        self.now = 0.0
        self.base = 0
        self.nextseqnum = 0
        self.expectedseqnum = 0
        self.rcv_base = 0
        self.buffer = {}
        self.acked = set()
        self.delivered = []
        self.timer_version = {}
        self.gbn_timer = 0
        self.tx_free = {'data': 0.0, 'ack': 0.0}
        self.last_arrival = {'data': 0.0, 'ack': 0.0}
        self.attempts = {}
        self.forced_losses = set(forced_losses or [])
        self.stats = dict(data_transmitted=0, retransmissions=0, acks_transmitted=0,
                          losses=0, corruptions=0, delays=0, timeouts=0)

    def log(self, event, message):
        if self.log_output is not None:
            self.log_output(f'{self.now:10.6f} {event:12s} {message}')

    def schedule(self, when, callback, *args):
        self.event_id += 1
        heapq.heappush(self.events, (when, self.event_id, callback, args))

    def payload(self, number):
        # this is application data. the receiver never uses it to choose a window.
        return struct.pack('!I', number) + (b'rescue update; ' * 70)[:989]

    def data_frame(self, number):
        return make_frame(0, number % self.m, self.payload(number))

    def window_note(self):
        sender = [(self.base + j) % self.m for j in range(self.c.window)]
        start = self.expectedseqnum if self.c.protocol == 'gbn' else self.rcv_base
        receiver = [start % self.m] if self.c.protocol == 'gbn' else [
            (start + j) % self.m for j in range(self.c.window)]
        return (f'base={self.base} nextseqnum={self.nextseqnum} '
                f'expectedseqnum={self.expectedseqnum} rcv_base={self.rcv_base} '
                f'sender_window={sender} receiver_window={receiver}')

    def channel(self, direction, frame, number):
        key = (direction, number)
        attempt = self.attempts.get(key, 0) + 1
        self.attempts[key] = attempt
        label = f'{direction} id={number} seq={number % self.m} attempt={attempt}'
        # even a lost packet occupies its transmission time on the link.
        start = max(self.now, self.tx_free[direction])
        finish = start + len(frame) * 8 / self.c.rate
        self.tx_free[direction] = finish
        lost = self.rng.random() < self.c.loss
        corrupt = self.rng.random() < self.c.corruption
        delayed = self.rng.random() < self.c.delay
        if lost or (direction, number, attempt) in self.forced_losses:
            self.stats['losses'] += 1
            self.log('loss', label)
            return
        if corrupt:
            changed = bytearray(frame)
            pos = self.rng.randrange(len(changed))
            changed[pos] ^= 1 << self.rng.randrange(8)
            frame = bytes(changed)
            self.stats['corruptions'] += 1
            self.log('corruption', f'{label} byte={pos}; checksum left unchanged')
        extra = self.c.extra_delay if delayed else 0.0
        if delayed:
            self.stats['delays'] += 1
            self.log('delay', f'{label} extra={extra:.3f}s')
        # fifo in each direction: late packets hold up later arrivals.
        # this models a queued satellite path without arbitrary packet reordering.
        arrival = max(finish + self.c.rtt / 2 + extra,
                      self.last_arrival[direction] + 1e-9)
        self.last_arrival[direction] = arrival
        callback = self.receive_data if direction == 'data' else self.receive_ack
        self.schedule(arrival, callback, frame)

    def send_data(self, number, retransmit=False):
        self.stats['data_transmitted'] += 1
        if retransmit:
            self.stats['retransmissions'] += 1
        event = 'retransmit' if retransmit else 'send'
        self.log(event, f'data id={number} seq={number % self.m}; {self.window_note()}')
        self.channel('data', self.data_frame(number), number)
        if self.c.protocol == 'sr':
            version = self.timer_version.get(number, 0) + 1
            self.timer_version[number] = version
            self.schedule(self.now + self.c.timeout, self.sr_timeout, number, version)

    def fill_window(self):
        was_empty = self.base == self.nextseqnum
        while (self.nextseqnum < self.c.packets
               and self.nextseqnum < self.base + self.c.window):
            number = self.nextseqnum
            self.nextseqnum += 1
            self.send_data(number)
        if self.c.protocol == 'gbn' and was_empty and self.base < self.nextseqnum:
            self.start_gbn_timer()

    def start_gbn_timer(self):
        # old heap entries stay there but their version makes them inactive.
        self.gbn_timer += 1
        self.schedule(self.now + self.c.timeout, self.gbn_timeout, self.gbn_timer)

    def gbn_timeout(self, version):
        if version != self.gbn_timer or self.base == self.nextseqnum:
            return
        self.stats['timeouts'] += 1
        self.log('timeout', f'oldest unacked id={self.base}')
        for number in range(self.base, self.nextseqnum):
            self.send_data(number, retransmit=True)
        self.start_gbn_timer()

    def sr_timeout(self, number, version):
        if (self.timer_version.get(number) != version
                or number < self.base or number in self.acked):
            return
        self.stats['timeouts'] += 1
        self.log('timeout', f'unacked id={number} seq={number % self.m}')
        self.send_data(number, retransmit=True)

    def send_ack(self, number):
        self.stats['acks_transmitted'] += 1
        rule = 'cumulative' if self.c.protocol == 'gbn' else 'individual'
        self.log('ack send', f'{rule} ack={number % self.m}; {self.window_note()}')
        self.channel('ack', make_frame(1, number % self.m), number)

    def deliver(self, payload):
        self.delivered.append(payload)
        self.log('deliver', f'application position={len(self.delivered) - 1}')

    def receive_data(self, frame):
        self.log('receive', 'data frame arrived')
        parsed = read_frame(frame)
        if parsed is None:
            self.log('checksum', 'bad data frame; discard')
            if self.c.protocol == 'gbn':
                self.send_ack(self.expectedseqnum - 1)
            return
        kind, seq, payload = parsed
        if kind != 0 or seq >= self.m:
            self.log('discard', 'invalid data header')
            return
        if self.c.protocol == 'gbn':
            if seq == self.expectedseqnum % self.m:
                self.deliver(payload)
                self.expectedseqnum += 1
            else:
                self.log('discard', f'out-of-order seq={seq}; '
                         f'expectedseqnum={self.expectedseqnum % self.m}')
            self.send_ack(self.expectedseqnum - 1)
            return
        distance = (seq - self.rcv_base) % self.m
        if distance < self.c.window:
            number = self.rcv_base + distance
            if number not in self.buffer:
                self.buffer[number] = payload
                self.log('buffer', f'seq={seq}; rcv_base={self.rcv_base % self.m}')
            else:
                self.log('duplicate', f'seq={seq} already buffered')
            self.send_ack(number)
            while self.rcv_base in self.buffer:
                self.deliver(self.buffer.pop(self.rcv_base))
                self.rcv_base += 1
            self.log('window', self.window_note())
        elif (self.rcv_base - seq) % self.m <= self.c.window:
            # an earlier ack may have been lost, so acknowledge the duplicate.
            self.log('duplicate', f'previous receiver window seq={seq}')
            self.send_ack(self.rcv_base - ((self.rcv_base - seq) % self.m))
        else:
            self.log('discard', f'seq={seq} outside receiver window')

    def receive_ack(self, frame):
        self.log('ack receive', 'ack frame arrived')
        parsed = read_frame(frame)
        if parsed is None:
            self.log('checksum', 'bad ack frame; discard')
            return
        kind, seq, _ = parsed
        if kind != 1 or seq >= self.m:
            self.log('discard', 'invalid ack header')
            return
        distance = (seq - self.base) % self.m
        if distance >= self.nextseqnum - self.base:
            self.log('ack ignore', f'duplicate/stale ack={seq}')
            return
        number = self.base + distance
        if self.c.protocol == 'gbn':
            self.base = number + 1
            self.gbn_timer += 1
            if self.base < self.nextseqnum:
                self.start_gbn_timer()
        else:
            self.acked.add(number)
            self.timer_version.pop(number, None)
            while self.base in self.acked:
                self.acked.remove(self.base)
                self.base += 1
        self.log('window', self.window_note())
        self.fill_window()

    def run(self):
        self.fill_window()
        processed = 0
        while self.base < self.c.packets:
            if not self.events or processed >= self.c.max_events:
                raise RuntimeError('transfer did not finish; check probabilities/timeout/event limit')
            self.now, _, callback, args = heapq.heappop(self.events)
            callback(*args)
            processed += 1
        # only the test oracle reads payload identities. protocol logic uses seq only.
        expected = [self.payload(i) for i in range(self.c.packets)]
        if self.delivered != expected:
            raise AssertionError('delivery is missing, duplicated, corrupted, or out of order')
        return dict(protocol=self.c.protocol, seed=self.c.seed, **self.stats,
                    delivered=len(self.delivered), simulation_seconds=round(self.now, 6),
                    throughput_bps=round(self.c.packets * 8000 / self.now, 3),
                    delivery_verified=True)


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--protocol', choices=['gbn', 'sr'], default='sr')
    p.add_argument('--packets', type=int, default=200)
    p.add_argument('--window', type=int, default=4)
    p.add_argument('--bits', type=int, default=3)
    p.add_argument('--loss', type=float, default=0)
    p.add_argument('--corruption', type=float, default=0)
    p.add_argument('--delay', type=float, default=0)
    p.add_argument('--timeout', type=float, default=1)
    p.add_argument('--seed', type=int, required=True, help='last four roll-number digits')
    p.add_argument('--extra-delay', type=float, default=0.35)
    p.add_argument('--rate', type=float, default=2_000_000)
    p.add_argument('--rtt', type=float, default=0.5)
    p.add_argument('--max-events', type=int, default=2_000_000)
    p.add_argument('--log', type=Path, help='also save the full event log')
    p.add_argument('--quiet', action='store_true', help='suppress console events, not file events')
    p.add_argument('--json', type=Path, help='save metrics and configuration as json')
    p.add_argument('--drop-packet-2', action='store_true', help='lose only the first send of data 2')
    return p


def main():
    args = parser().parse_args()
    config = Config(**{name: getattr(args, name) for name in Config.__dataclass_fields__})
    stream = None
    if args.log:
        args.log.parent.mkdir(parents=True, exist_ok=True)
        stream = args.log.open('w', encoding='utf-8')

    def write(line):
        if not args.quiet:
            print(line)
        if stream:
            stream.write(line + '\n')

    try:
        result = Simulator(config, write, [('data', 2, 1)] if args.drop_packet_2 else []).run()
        if args.json:
            args.json.parent.mkdir(parents=True, exist_ok=True)
            args.json.write_text(json.dumps(dict(config=asdict(config), results=result), indent=2) + '\n')
        print(json.dumps(result, indent=2))
    except (ValueError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from exc
    finally:
        if stream:
            stream.close()


if __name__ == '__main__':
    main()
