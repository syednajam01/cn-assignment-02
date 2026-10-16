"""run the experiments, draw the figures, and build the four-page report."""

import argparse
import csv
from dataclasses import asdict
import json
from pathlib import Path
import zipfile

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, PageBreak,
                                Table, TableStyle, Image)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from simulator import Config, Simulator

root = Path(__file__).resolve().parent
out = root / 'results'


def run_experiments(seed):
    out.mkdir(exist_ok=True)
    (out / 'logs').mkdir(exist_ok=True)
    rows = []
    configs = {}
    cases = [('A', 0, 0, 0), ('B', .10, 0, 0), ('C', .05, .05, .10)]
    for case, loss, corruption, delay in cases:
        for protocol in ('gbn', 'sr'):
            config = Config(protocol=protocol, seed=seed, loss=loss,
                            corruption=corruption, delay=delay)
            with (out / 'logs' / f'{case}_{protocol}.log').open('w') as stream:
                result = Simulator(config, lambda line: stream.write(line + '\n')).run()
            row = dict(case=case, **result)
            rows.append(row)
            configs[f'{case}_{protocol}'] = asdict(config)
    with (out / 'results.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
    (out / 'results.json').write_text(json.dumps(dict(configs=configs, results=rows), indent=2) + '\n')
    return rows


def make_graph(rows, status):
    fig, axes = plt.subplots(1, 2, figsize=(9, 3.1))
    for j, (field, ylabel, title) in enumerate([
        ('retransmissions', 'data retransmissions (packets)', 'Retransmission cost'),
        ('simulation_seconds', 'simulated completion time (s)', 'Completion time')
    ]):
        ax = axes[j]
        for i, (protocol, color) in enumerate([('gbn', '#23628a'), ('sr', '#cf743a')]):
            values = [r[field] for r in rows if r['protocol'] == protocol]
            bars = ax.bar([x + (i - .5) * .34 for x in range(3)], values,
                          width=.34, color=color, label=protocol.upper())
            ax.bar_label(bars, fmt='%g' if j == 0 else '%.1f', fontsize=8, padding=3)
        ax.set_xticks(range(3), ['A: reliable', 'B: loss', 'C: mixed'])
        ax.set_ylabel(ylabel, fontsize=9)
        ax.set_title(title, fontsize=11)
        ax.set_ylim(0, max(r[field] for r in rows) * 1.2 + 1)
        ax.spines[['top', 'right']].set_visible(False)
        ax.legend(fontsize=8)
    fig.suptitle(f'200 packets | N=4 | k=3 | {status}', fontsize=10)
    fig.tight_layout()
    fig.savefig(out / 'gbn_vs_sr.png', dpi=180)
    fig.savefig(out / 'gbn_vs_sr.svg')
    plt.close(fig)


def make_diagram():
    fig, ax = plt.subplots(figsize=(9, 2.55))
    ax.axis('off')
    ax.set_xlim(-2.8, 8.3)
    ax.set_ylim(-.5, 3.4)
    for y, label, window in [(2.2, 'old window, N=5', {0, 1, 2, 3, 4}),
                              (.7, 'new window, N=5', {5, 6, 7, 0, 1})]:
        ax.text(-2.65, y+.3, label, fontsize=10, va='center')
        for i, seq in enumerate(range(8)):
            ax.add_patch(Rectangle((i, y), .87, .6, facecolor='#f3ccae' if seq in window else '#edf0f2',
                                   edgecolor='#555555', linewidth=.6))
            ax.text(i+.435, y+.3, str(seq), ha='center', va='center', fontsize=11)
    ax.annotate('0 and 1 overlap', xy=(.44, 1.3), xytext=(2.4, 1.65), fontsize=10,
                arrowprops=dict(arrowstyle='->', color='#993b27'))
    ax.text(-2.65, 3.08, 'Receiver accepts old 0-4, but their ACKs are lost.', fontsize=10)
    ax.text(-2.65, -.25, 'Sender retries old 0. Receiver now accepts 0 again as new data: ambiguity.', fontsize=10)
    fig.tight_layout(pad=.3)
    fig.savefig(out / 'sr_ambiguity.png', dpi=180)
    fig.savefig(out / 'sr_ambiguity.svg')
    plt.close(fig)


# each row is an event, or an explicitly named burst of consecutive events.
# the ungrouped simulator event logs are saved alongside these compact tables.
gbn_trace = [
    ['Send initial burst', '0,1,2,3', 'Deliver 0,1; lose 2; discard 3', 'Send 0,1,1', 'S[0-3]; E=2'],
    ['Receive ACK0; send 4', '4', 'In flight', 'Apply 0', 'S[1-4]; E=2'],
    ['Receive ACK1; send 5', '5', 'In flight', 'Apply 1', 'S[2-5]; E=2'],
    ['Receive duplicate ACK1', '-', 'Waiting for 2', 'Ignore 1', 'S[2-5]; E=2'],
    ['4 reaches receiver', '4', 'Discard out of order', 'Send 1', 'S[2-5]; E=2'],
    ['5 reaches receiver', '5', 'Discard out of order', 'Send 1', 'S[2-5]; E=2'],
    ['Duplicate ACKs arrive', '-', 'Waiting for 2', 'Ignore 1,1', 'S[2-5]; E=2'],
    ['Timer for 2 expires', '2,3,4,5', 'Resend all outstanding', '-', 'S[2-5]; E=2'],
    ['Retries reach receiver', '2,3,4,5', 'Deliver 2,3,4,5 in order', 'Send 2,3,4,5', 'S[2-5]; E=6'],
    ['Receive ACK2; send 6', '6', 'In flight', 'Apply 2', 'S[3-6]; E=6'],
    ['Receive ACK3; send 7', '7', 'In flight', 'Apply 3', 'S[4-7]; E=6'],
    ['Receive ACK4; send 8', '8', 'In flight', 'Apply 4', 'S[5-8]; E=6'],
    ['Receive ACK5; send 9', '9', 'In flight', 'Apply 5', 'S[6-9]; E=6'],
    ['Final burst arrives', '6,7,8,9', 'Deliver 6,7,8,9', 'Send 6,7,8,9', 'S[6-9]; E=10'],
    ['Receive ACK6', '-', 'All delivered', 'Apply 6', 'S[7-9]; E=10'],
    ['Receive ACK7', '-', 'All delivered', 'Apply 7', 'S[8-9]; E=10'],
    ['Receive ACK8', '-', 'All delivered', 'Apply 8', 'S[9]; E=10'],
    ['Receive ACK9', '-', 'All delivered', 'Apply 9', 'S empty; E=10'],
]
sr_trace = [
    ['Send initial burst', '0,1,2,3', 'Deliver 0,1; lose 2; buffer 3', 'Send 0,1,3', 'S[0-3]; R[2-5]'],
    ['Receive ACK0; send 4', '4', 'In flight; buffer={3}', 'Mark 0', 'S[1-4]; R[2-5]'],
    ['Receive ACK1; send 5', '5', 'In flight; buffer={3}', 'Mark 1', 'S[2-5]; R[2-5]'],
    ['Receive ACK3', '-', 'Still waiting for 2', 'Mark 3', 'S[2-5]; R[2-5]'],
    ['4 reaches receiver', '4', 'Buffer={3,4}; deliver nothing', 'Send 4', 'S[2-5]; R[2-5]'],
    ['5 reaches receiver', '5', 'Buffer={3,4,5}; deliver nothing', 'Send 5', 'S[2-5]; R[2-5]'],
    ['Receive ACK4 and ACK5', '-', 'Buffer={3,4,5}', 'Mark 4,5', 'S[2-5]; R[2-5]'],
    ['Timer for 2 expires', '2', 'Resend only missing packet 2', '-', 'S[2-5]; R[2-5]'],
    ['Retry 2 reaches receiver', '2', 'Deliver 2, then buffered 3,4,5', 'Send 2', 'S[2-5]; R[6-9]'],
    ['ACK2; send next burst', '6,7,8,9', 'In flight; buffer empty', 'Mark 2; base=6', 'S[6-9]; R[6-9]'],
    ['6 reaches receiver', '6', 'Deliver 6', 'Send 6', 'S[6-9]; R[7-10]'],
    ['7 reaches receiver', '7', 'Deliver 7', 'Send 7', 'S[6-9]; R[8-11]'],
    ['8 reaches receiver', '8', 'Deliver 8', 'Send 8', 'S[6-9]; R[9-12]'],
    ['9 reaches receiver', '9', 'Deliver 9', 'Send 9', 'S[6-9]; R[10-13]'],
    ['Receive ACK6', '-', 'All delivered', 'Mark 6', 'S[7-9]; R[10-13]'],
    ['Receive ACK7', '-', 'All delivered', 'Mark 7', 'S[8-9]; R[10-13]'],
    ['Receive ACK8', '-', 'All delivered', 'Mark 8', 'S[9]; R[10-13]'],
    ['Receive ACK9', '-', 'All delivered', 'Mark 9', 'S empty; R[10-13]'],
]


def save_traces(seed):
    for protocol, rows in [('gbn', gbn_trace), ('sr', sr_trace)]:
        with (out / f'task2_{protocol}_trace.csv').open('w', newline='') as stream:
            writer = csv.writer(stream)
            writer.writerow(['event', 'sender', 'packet', 'receiver', 'ack', 'window'])
            writer.writerows([[i, *row] for i, row in enumerate(rows, 1)])
        with (out / 'logs' / f'task2_{protocol}.log').open('w') as stream:
            result = Simulator(Config(protocol=protocol, packets=10, bits=4, seed=seed, timeout=1.5),
                               lambda line: stream.write(line + '\n'), [('data', 2, 1)]).run()
            stream.write(json.dumps(result) + '\n')


def build_report(rows, status):
    fonts = Path(matplotlib.get_data_path()) / 'fonts' / 'ttf'
    for name, filename in [('note_sans', 'DejaVuSans.ttf'),
                           ('note_bold', 'DejaVuSans-Bold.ttf'),
                           ('note_italic', 'DejaVuSans-Oblique.ttf'),
                           ('note_bolditalic', 'DejaVuSans-BoldOblique.ttf'),
                           ('note_mono', 'DejaVuSansMono.ttf')]:
        pdfmetrics.registerFont(TTFont(name, str(fonts / filename)))
    pdfmetrics.registerFontFamily('note_sans', normal='note_sans', bold='note_bold',
                                  italic='note_italic', boldItalic='note_bolditalic')
    styles = getSampleStyleSheet()
    for style in styles.byName.values():
        style.fontName = 'note_bold' if style.name.startswith('Heading') else 'note_sans'
    styles.add(ParagraphStyle(name='body_note', fontName='note_sans', fontSize=9.0,
                              leading=12, spaceAfter=6))
    styles.add(ParagraphStyle(name='small_note', fontName='note_sans', fontSize=7.8,
                              leading=10, spaceAfter=4))
    styles.add(ParagraphStyle(name='cell_note', fontName='note_sans', fontSize=6.5, leading=8))
    styles['Heading1'].fontSize = 16
    styles['Heading1'].leading = 19
    styles['Heading2'].fontSize = 11
    styles['Heading2'].leading = 14
    story = []

    def p(text, style='body_note'):
        story.append(Paragraph(text, styles[style]))

    def table(data, widths, small=False):
        style = 'cell_note' if small else 'small_note'
        cells = [[Paragraph(str(cell), styles[style]) for cell in row] for row in data]
        t = Table(cells, colWidths=widths, repeatRows=1, hAlign='LEFT')
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#dce8ef')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('GRID', (0, 0), (-1, -1), .25, colors.HexColor('#bbc7ce')),
            ('LEFTPADDING', (0, 0), (-1, -1), 4),
            ('RIGHTPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 3 if not small else 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3 if not small else 2),
        ]))
        story.append(t)

    p('Reliable transfer for a disaster-response network', 'Heading1')
    p('CS3001 Computer Networks | Assignment II | Fall 2026', 'small_note')
    p(status, 'small_note')
    p('Task 1: scenario and protocol choice', 'Heading2')
    p('<b>1. Why reliability matters.</b> Rescue assignments must reach the correct team without changed coordinates or missing instructions. '
      'Casualty lists and supply requests must also arrive correctly and in order, because incomplete or repeated information can affect rescue decisions.')
    p('<b>2. Why Stop-and-Wait wastes capacity.</b> One 1,000-byte packet takes only 4 ms to transmit, but the satellite round trip takes 500 ms. '
      'The sender therefore spends most of each cycle waiting for an ACK instead of sending useful rescue data.')
    p('<b>3. Why pipelining helps.</b> A sender window allows several packets to be in flight while earlier ACKs are returning. '
      'This makes better use of the long satellite path and lets rescue updates leave the sender more quickly.')
    p('<b>4. Protocol choice: SR.</b> SR retransmits only an unacknowledged packet, so a single loss wastes less of the limited satellite bandwidth. '
      'Its receiver buffers valid out-of-order packets and delivers them when the gap is filled, whereas GBN discards them and sends them again. '
      'The extra receiver memory and per-packet timer bookkeeping are reasonable for a four-packet window.')
    p('Task 3: implementation and approach', 'Heading2')
    p('The program uses a priority queue of events rather than real sleeping or sockets. Both protocols build packets with a 16-bit Internet checksum, '
      'send them through the same channel implementation, check received frames and recover through ACKs and timeouts. No reliable-transport library is used.')
    p('<b>GBN:</b> base identifies the oldest unacknowledged packet and nextseqnum identifies the next packet to send. '
      'The receiver accepts only expectedseqnum and sends the sequence number of its last in-order packet as a cumulative ACK. '
      'One logical timer tracks base; on expiry all outstanding packets are resent, and on progress the timer restarts for the new base.')
    p('<b>SR:</b> the sender remembers individual ACKs and maintains a timer for each unacknowledged packet. '
      'The receiver checks its window starting at rcv_base, buffers valid packets and delivers only a consecutive prefix. '
      'Duplicates in the previous receiver window are ACKed again, allowing recovery when an ACK is lost.')
    p('Assumptions and measurement rules', 'Heading2')
    p('The link is full duplex at 2 Mbps per direction, with 250 ms one-way propagation. A data frame is exactly 1,000 bytes '
      '(993 bytes of application data and a 7-byte header/checksum); an ACK is 7 bytes. Transmission time and per-direction serialization are modeled. '
      'Loss, corruption and delay are independent draws per transmission, applied equally to data and ACKs; a dropped frame does not arrive.', 'small_note')
    p('The channel is FIFO in each direction: selected delays add 350 ms, and later arrivals wait behind a delayed frame. '
      'This queued-path assumption avoids arbitrary stale packets surviving sequence reuse; unlimited reordering would require a packet-lifetime rule. '
      'The timeout is 1 s. GBN requires N &lt; 2^k and SR requires N &lt;= 2^(k-1). Absolute counters are local bookkeeping only; '
      'receivers and ACK processing decide from modulo sequence numbers, never application packet identities.', 'small_note')
    p('Completion time is simulated seconds until the final required ACK reaches the sender. Transmitted packets count data attempts, including losses and retries; '
      'ACK attempts are reported separately in CSV/JSON. Reported throughput is 200 x 8,000 / completion time (useful data-frame bits/s, excluding retries and ACKs). '
      'Application-byte goodput would instead use 993 bytes per delivered packet.', 'small_note')

    story.append(PageBreak())
    p('Task 2: packet traces, N = 4', 'Heading1')
    p('Assume immediate window refilling, no other faults, and a 1.5 s timeout for this trace, so ACKs of 3-5 return before packet 2 times out. '
      'ACKs below identify the received packet (not the next expected packet). S is the sender window; R is the SR receiver window; E is GBN expectedseqnum. '
      'Consecutive bursts are grouped; full send/receive/ACK event logs and the tables are included separately.', 'small_note')
    p('Go-Back-N: cumulative ACKs; receiver window size 1', 'Heading2')
    head = ['Event / sender', 'Packet', 'Receiver', 'ACK', 'Window after event']
    table([head] + [[f'{i}. {row[0]}', *row[1:]] for i, row in enumerate(gbn_trace, 1)],
          [133, 43, 168, 74, 105], small=True)
    p('Selective Repeat: individual ACKs; receiver buffers 3-5', 'Heading2')
    table([head] + [[f'{i}. {row[0]}', *row[1:]] for i, row in enumerate(sr_trace, 1)],
          [133, 43, 168, 74, 105], small=True)
    p('<b>Retransmissions: GBN = 4 (2,3,4,5), SR = 1 (2).</b> ACK0 and ACK1 open slots for 4 and 5 before the timeout. '
      'GBN discards 3-5 and resends the whole outstanding window; SR has already buffered and acknowledged 3-5. '
      'Sender windows near completion are clipped to the remaining packets; R ranges above 9 are logical positions, not extra data sent. '
      'Task 2 uses the given unique labels 0-9; executable traces use k=4, while Task 4 uses modulo-8 numbering.', 'small_note')

    story.append(PageBreak())
    p('Task 4: experiments and comparison', 'Heading1')
    p(f'{status}. Each protocol starts with the same seed and parameters: 200 packets, N=4, k=3, timeout=1 s. '
      'A: no faults. B: loss=0.10, corruption=0, delay=0. C: loss=0.05, corruption=0.05, delay=0.10. '
      'The RNG is reset for each run; protocols consume draws differently when their send histories differ.', 'small_note')
    data = [['Case', 'Protocol', 'Data sent', 'Retries', 'Delivered', 'Time (s)', 'Throughput (kbps)']]
    for row in rows:
        data.append([row['case'], row['protocol'].upper(), row['data_transmitted'], row['retransmissions'],
                     row['delivered'], f"{row['simulation_seconds']:.6f}", f"{row['throughput_bps']/1000:.3f}"])
    table(data, [35, 55, 64, 55, 64, 100, 150])
    story.append(Spacer(1, 12))
    story.append(Image(str(out / 'gbn_vs_sr.png'), width=523, height=180))
    p('What the runs show', 'Heading2')
    p('On the reliable channel, both protocols deliver all 200 packets without retransmissions and finish at the same simulated time. '
      'With faults, GBN can resend valid packets behind a gap because its receiver discards them, while SR keeps them and usually needs fewer retries. '
      'An ACK loss can still cause an SR retransmission even when the data was delivered, and delay can trigger a timeout if an ACK arrives too late. '
      'These are single seeded runs, not an average over many trials; their exact counts depend on the fault stream and channel assumptions.')
    p('Checks performed', 'Heading2')
    p('The receiver output is compared byte for byte with the original ordered application messages at the end of every run. '
      'The tests also cover single-bit checksum errors in data and ACKs, clean-channel wraparound, the Task 2 retransmission counts, '
      'lost ACKs, loss at a sequence wrap, mixed faults across 15 seeds and three window sizes, GBN\'s largest legal window, invalid windows and total-loss failure. '
      'A configurable event limit prevents an unreachable channel from running forever.')
    p('How to reproduce', 'Heading2')
    p('Create/activate a virtual environment, install requirements.txt, then run: '
      '<font name="note_mono">python prepare_submission.py --roll YOUR_ROLL_NUMBER</font>. '
      'The last four digits are extracted as the seed. This rebuilds all six runs, logs, CSV/JSON, trace tables, figures, this report and the submission ZIP. '
      'Use <font name="note_mono">python -m unittest -v</font> for the checks. The simulator itself uses only the Python standard library.')

    story.append(PageBreak())
    p('Task 5: transport-layer analysis', 'Heading1')
    p('1. Pipelining and link utilization', 'Heading2')
    p('L = 1,000 bytes x 8 = 8,000 bits; R = 2,000,000 bits/s; RTT = 0.500 s.<br/>'
      'Transmission time L/R = 8,000 / 2,000,000 = <b>0.004 s = 4 ms</b>.<br/>'
      'Stop-and-Wait: U = (L/R) / (RTT + L/R) = 0.004 / 0.504 = <b>0.0079365 = 0.79365%</b>.<br/>'
      'With a four-packet pipeline: U = min(1, N(L/R)/(RTT + L/R))<br/>'
      '= min(1, 4 x 0.004 / 0.504) = <b>0.031746 = 3.17460%</b>.')
    p('The four-packet window improves ideal utilization by a factor of four because it sends four packets per ACK cycle instead of one. '
      'Ideal useful frame throughput rises from 15.873 kbps to 63.492 kbps. These slide calculations ignore ACK serialization, errors and extra delays; '
      'the simulator includes a 28-microsecond ACK transmission time, so its clean throughput is slightly lower. '
      'Even N=4 leaves much of this high-delay link unused; approximately 126 packets in flight would be needed for ideal full utilization.')
    p('2. SR sequence numbers and safe window', 'Heading2')
    p('<b>(a)</b> Three bits provide 2^3 = <b>8 sequence numbers: 0-7</b>.<br/>'
      '<b>(b)</b> The maximum safe SR window is half the sequence space: N &lt;= 2^(3-1) = <b>4 packets</b>.<br/>'
      '<b>(c)</b> If N=5, suppose the receiver accepts old packets 0-4, but all five ACKs are lost. '
      'Its next receiver window becomes [5,6,7,0,1], while the sender is still waiting for ACKs for the original window. '
      'When old packet 0 is retransmitted, sequence number 0 is inside the new window, so the receiver cannot distinguish it from a new packet 0.')
    story.append(Image(str(out / 'sr_ambiguity.png'), width=523, height=148))
    p('The old and new windows overlap at 0 and 1. For equal sender and receiver window sizes, 2N &lt;= 8 prevents that overlap. '
      'As with the textbook protocols, the model also assumes old traffic cannot survive indefinitely across later reuse of the same sequence numbers.', 'small_note')
    p('Conclusion', 'Heading2')
    p('SR is the better choice for this disaster-response link because it avoids resending valid out-of-order rescue updates. '
      'Both implementations preserve in-order, duplicate-free delivery under the stated channel model, while the checksums detect the injected corruption. '
      'The small window limits utilization even when the channel is reliable, so reliability and pipeline sizing both matter.')
    p('Submission and demonstration', 'Heading2')
    p('Submit RollNo_A2.zip and a viewable Drive link to a short working video. Demonstrate a clean run, the forced packet-2 loss for both protocols, '
      'a mixed-fault run and a changed legal window size; explain one timeout, cumulative versus individual ACKs and SR buffering. '
      'Check the course portal for the deadline because the assignment sheet leaves it blank.', 'small_note')

    def footer(canvas, doc):
        canvas.setFont('note_sans', 8)
        canvas.setFillColor(colors.HexColor('#52616b'))
        canvas.drawString(36, 21, 'CS3001 | reliable data transfer')
        canvas.drawRightString(559, 21, f'{doc.page} / 4')

    doc = SimpleDocTemplate(str(out / 'report.pdf'), pagesize=(595.28, 841.89),
                            leftMargin=36, rightMargin=36, topMargin=30, bottomMargin=36)
    doc.build(story, onFirstPage=footer, onLaterPages=footer)
    if doc.page > 4:
        raise RuntimeError(f'report is {doc.page} pages; shorten it before submission')


def make_zip(roll):
    dest = root / 'dist'
    dest.mkdir(exist_ok=True)
    name = f'{roll}_A2.zip' if roll else 'PROVISIONAL_A2.zip'
    with zipfile.ZipFile(dest / name, 'w', zipfile.ZIP_DEFLATED) as archive:
        for folder in [root, out, out / 'logs', root / 'docs']:
            if not folder.exists():
                continue
            for path in sorted(folder.iterdir()):
                if (path.is_file() and (not path.name.startswith('.') or path.name == '.gitignore')
                        and path.suffix != '.zip'):
                    archive.write(path, path.relative_to(root))
    return dest / name


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument('--roll', help='your actual roll number, e.g. 23K-1234')
    group.add_argument('--provisional', action='store_true', help='use clearly labelled temporary seed 0000')
    args = parser.parse_args()
    if args.roll:
        digits = ''.join(ch for ch in args.roll if ch.isdecimal() and ch.isascii())
        if len(digits) < 4 or any(ch in args.roll for ch in '/\\'):
            parser.error('roll number must contain at least four digits and no path separators')
        seed = int(digits[-4:])
        status = f'Roll: {args.roll} | seed: {digits[-4:]}'
    else:
        seed = 0
        status = 'PROVISIONAL seed 0000: regenerate with your roll number before submission'
    rows = run_experiments(seed)
    make_graph(rows, status)
    make_diagram()
    save_traces(seed)
    build_report(rows, status)
    (out / 'seed_status.txt').write_text(status + '\n')
    path = make_zip(args.roll)
    print(status)
    for row in rows:
        print(f"{row['case']} {row['protocol']:3s} sent={row['data_transmitted']} "
              f"retries={row['retransmissions']} delivered={row['delivered']} "
              f"time={row['simulation_seconds']:.6f}s")
    print(f'report: {out / "report.pdf"}')
    print(f'zip: {path}')


if __name__ == '__main__':
    main()
