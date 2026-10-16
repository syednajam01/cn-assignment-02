"""run with: python -m unittest -v"""

import unittest
from simulator import Config, Simulator, checksum, make_frame, read_frame


class ProtocolTests(unittest.TestCase):
    def test_checksum_detects_bit_changes(self):
        for kind, payload in [(0, b'casualty list'), (1, b'')]:
            frame = make_frame(kind, 3, payload)
            self.assertEqual(checksum(frame), 0)
            for i in range(len(frame)):
                damaged = bytearray(frame)
                damaged[i] ^= 1
                self.assertIsNone(read_frame(bytes(damaged)))

    def test_exact_packet_length(self):
        self.assertEqual(len(Simulator(Config()).data_frame(0)), 1000)

    def test_clean_channel_and_many_wraps(self):
        for protocol in ['gbn', 'sr']:
            sim = Simulator(Config(protocol=protocol, packets=200))
            result = sim.run()
            self.assertEqual(result['delivered'], 200)
            self.assertEqual(result['retransmissions'], 0)
            self.assertEqual(result['data_transmitted'], 200)

    def test_task_two_retransmissions(self):
        for protocol, retransmissions in [('gbn', 4), ('sr', 1)]:
            sim = Simulator(Config(protocol=protocol, packets=10, bits=4, timeout=1.5),
                            forced_losses=[('data', 2, 1)])
            result = sim.run()
            self.assertEqual(result['retransmissions'], retransmissions)

    def test_lost_ack_and_data_near_wrap(self):
        for protocol in ['gbn', 'sr']:
            for fault in [[('ack', 0, 1)], [('ack', 7, 1)], [('data', 7, 1)]]:
                sim = Simulator(Config(protocol=protocol, packets=30), forced_losses=fault)
                result = sim.run()
                self.assertEqual(result['delivered'], 30)

    def test_mixed_errors_across_seeds_and_windows(self):
        for protocol in ['gbn', 'sr']:
            for window in [1, 2, 4]:
                for seed in range(15):
                    sim = Simulator(Config(protocol=protocol, packets=80, window=window,
                                           loss=0.1, corruption=0.08, delay=0.15,
                                           seed=seed, timeout=0.8))
                    self.assertTrue(sim.run()['delivery_verified'])

    def test_gbn_largest_window(self):
        sim = Simulator(Config(protocol='gbn', packets=80, window=7,
                               loss=0.1, delay=0.1, corruption=0.1, seed=12))
        self.assertTrue(sim.run()['delivery_verified'])

    def test_invalid_windows(self):
        for protocol, window in [('sr', 5), ('gbn', 8)]:
            with self.assertRaises(ValueError):
                Simulator(Config(protocol=protocol, window=window))

    def test_total_loss_has_bounded_failure(self):
        with self.assertRaises(RuntimeError):
            Simulator(Config(loss=1, max_events=50)).run()


if __name__ == '__main__':
    unittest.main()
