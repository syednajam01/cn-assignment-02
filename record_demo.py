"""make a captioned video from real program output; requires ffmpeg on PATH."""

import argparse
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import textwrap

import matplotlib
from PIL import Image, ImageDraw, ImageFont

root = Path(__file__).resolve().parent


def execute(arguments):
    result = subprocess.run([sys.executable, 'simulator.py', *arguments], cwd=root,
                            text=True, capture_output=True, check=True)
    text = result.stdout
    start = text.rfind('\n{')
    metrics = json.loads(text[start+1:] if start >= 0 else text)
    events = text[:start].splitlines() if start >= 0 else []
    return events, metrics


def summary(result):
    return [f"data sent: {result['data_transmitted']}   retries: {result['retransmissions']}   "
            f"delivered: {result['delivered']}",
            f"simulation time: {result['simulation_seconds']:.6f} s   "
            f"in-order delivery verified: {result['delivery_verified']}"]


def brief(line):
    return line.split(';')[0]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seed', required=True, type=int)
    parser.add_argument('--provisional', action='store_true')
    args = parser.parse_args()
    if not shutil.which('ffmpeg'):
        parser.error('ffmpeg must be installed and available on PATH')
    common = ['--seed', str(args.seed)]
    slides = []
    clean_cmd = ['--protocol', 'sr', '--packets', '10', '--quiet', *common]
    _, clean = execute(clean_cmd)
    slides.append(('1. reliable channel', 'No loss, corruption or extra delay: no retries are needed.',
                   clean_cmd, summary(clean)))
    for protocol in ['gbn', 'sr']:
        command = ['--protocol', protocol, '--packets', '10', '--window', '4',
                   '--bits', '4', '--timeout', '1.5', '--drop-packet-2', *common]
        events, result = execute(command)
        if protocol == 'gbn':
            lines = [brief(line) for line in events
                     if any(word in line for word in [' loss ', ' discard ', ' timeout ', ' retransmit '])]
            title = '2. gbn: one gap, four retries'
            caption = 'Packet 2 is lost; 3-5 are discarded. The oldest-packet timeout resends 2-5.'
        else:
            lines = [brief(line) for line in events if any(word in line for word in
                     [' loss ', 'buffer       seq=3', 'buffer       seq=4', 'buffer       seq=5',
                      ' timeout ', ' retransmit ', 'deliver      application position=2',
                      'deliver      application position=3', 'deliver      application position=4',
                      'deliver      application position=5'])]
            title = '3. sr: buffer later data, retry only 2'
            caption = 'Individual ACKs keep 3-5 confirmed. Filling the gap delivers the buffered group.'
        slides.append((title, caption, command, lines[:11] + [''] + summary(result)))
    mixed_cmd = ['--protocol', 'sr', '--packets', '40', '--window', '4', '--bits', '3',
                 '--loss', '.05', '--corruption', '.05', '--delay', '.10', *common]
    events, result = execute(mixed_cmd)
    lines = [brief(line) for line in events if any(word in line for word in
             [' loss ', ' corruption ', ' checksum ', ' delay ', ' timeout ', ' retransmit '])]
    slides.append(('4. faults affect data and acks', 'Actual mixed-fault output excerpts; checksums reject bit flips.',
                   mixed_cmd, lines[:10] + [''] + summary(result)))
    changed_cmd = ['--protocol', 'sr', '--packets', '40', '--window', '2', '--bits', '3',
                   '--loss', '.25', *common]
    events, result = execute(changed_cmd)
    lines = [brief(line) for line in events if 'seq=0' in line and ' send ' in line][:5]
    slides.append(('5. change window and increase loss', 'N=2 remains safe; the sequence field wraps from 7 back to 0.',
                   changed_cmd, lines + [''] + summary(result)))
    tested = subprocess.run([sys.executable, '-m', 'unittest', '-v'], cwd=root,
                            text=True, capture_output=True, check=True)
    lines = (tested.stdout + tested.stderr).splitlines()
    lines = [line.replace(' (test_simulator.ProtocolTests.', ' (') for line in lines]
    slides.append(('6. run the checks', 'Tests include loss recovery, wraparound, checksum detection and safe windows.',
                   ['-m', 'unittest', '-v'], lines))
    slides.append(('7. read the results and submit', 'The figures and tables are generated from actual experiment runs.',
                   ['prepare_submission.py', '--roll', 'YOUR_ROLL_NUMBER'], [
                       'results/report.pdf: four-page report, Tasks 1-5',
                       'results/results.csv: six runs, data/ACK counts and completion time',
                       'results/gbn_vs_sr.png: retransmissions and time comparison',
                       'results/sr_ambiguity.png: why N=5 is unsafe with k=3',
                       'results/logs/: full send, receive, ACK and retry logs',
                       '', 'Regenerate with your actual roll number before submitting.',
                       'Submit dist/<roll>_A2.zip plus a viewable Drive video link.',
                       '', 'This video uses real stdout excerpts with captions; it has no narration.']))

    fonts = Path(matplotlib.get_data_path()) / 'fonts' / 'ttf'
    title_font = ImageFont.truetype(str(fonts / 'DejaVuSans-Bold.ttf'), 31)
    note_font = ImageFont.truetype(str(fonts / 'DejaVuSans.ttf'), 18)
    code_font = ImageFont.truetype(str(fonts / 'DejaVuSansMono.ttf'), 16)
    status = f'PROVISIONAL seed {args.seed:04d}' if args.provisional else f'seed {args.seed:04d}'
    dest = root / 'docs' / ('demo_provisional.mp4' if args.provisional else 'demo.mp4')
    dest.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='cn_demo_') as folder:
        folder = Path(folder)
        for i, (title, caption, command, lines) in enumerate(slides):
            canvas = Image.new('RGB', (1280, 720), '#101a25')
            draw = ImageDraw.Draw(canvas)
            draw.text((35, 25), title, font=title_font, fill='#f3f6fa')
            draw.text((35, 78), caption, font=note_font, fill='#b8d1df')
            draw.rounded_rectangle((25, 116, 1255, 662), radius=10, fill='#192836')
            prefix = 'python ' if command[0] in ('prepare_submission.py', '-m') else 'python simulator.py '
            cmd = textwrap.wrap('$ ' + prefix + ' '.join(command), width=120)
            y = 132
            for line in cmd:
                draw.text((40, y), line, font=code_font, fill='#8ddcb3')
                y += 23
            y += 12
            for line in lines:
                for wrapped in textwrap.wrap(line, width=120) or ['']:
                    if y <= 635:
                        color = '#ffbd86' if any(x in wrapped for x in ['retransmit', 'timeout', 'loss']) else '#e3ebf0'
                        draw.text((40, y), wrapped, font=code_font, fill=color)
                        y += 24
            draw.text((35, 680), f'CS3001 | {status} | actual execution excerpts | {i+1}/{len(slides)}',
                      font=note_font, fill='#b8d1df')
            canvas.save(folder / f'{i:02d}.png')
        subprocess.run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-y',
                        '-framerate', '1/9', '-i', str(folder / '%02d.png'), '-r', '15',
                        '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-crf', '23',
                        '-movflags', '+faststart', str(dest)], check=True)
    print(dest)


if __name__ == '__main__':
    main()
