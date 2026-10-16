# cn assignment 02

GBN and SR over a simulated satellite link. The transport code is written from scratch in Python; there is no ready-made reliable-transport library.

**The results and video use roll number 0611 and random seed 611 (the integer value of 0611).**

video link : "https://drive.google.com/file/d/1RrtKoboo80VVcFxFKobq5ezko-mzP_3B/view?usp=sharing"

## run on windows

Python 3.10 or newer is needed. Open PowerShell in the folder where you want the project:

```powershell
git clone https://github.com/syednajam01/cn-assignment-02.git
cd cn-assignment-02
py -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

The next command is one mixed-error sample run. The seed below uses the supplied roll number, `0611`:

```powershell
.\.venv\Scripts\python.exe simulator.py --protocol sr --packets 200 --window 4 --bits 3 --loss 0.05 --corruption 0.05 --delay 0.10 --timeout 1 --seed 0611 --log results\my_sr.log
```

Using the environment's Python directly works even when PowerShell blocks activation scripts. Activation is optional:

```powershell
.\.venv\Scripts\Activate.ps1
python simulator.py --protocol gbn --seed 0611
```

## run on linux or macos

```bash
git clone https://github.com/syednajam01/cn-assignment-02.git
cd cn-assignment-02
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python simulator.py --protocol sr --seed 0611
```

The simulator and tests use only the standard library. Matplotlib and ReportLab are needed only for generating the graph and report. A working `.venv` was created in the development workspace; it is intentionally excluded from Git and the ZIP because virtual environments contain machine-specific paths. Recreate it with the commands above after cloning.

## make the final submission

The supplied roll number is `0611`. Use it below; substitute your full university roll number if the ZIP filename requires a campus/year prefix. The script extracts its last four digits, reruns the six experiments, creates the graph and ambiguity diagram, rebuilds the four-page report, and packages the files:

```powershell
.\.venv\Scripts\python.exe -m unittest -v
.\.venv\Scripts\python.exe prepare_submission.py --roll 0611
```

The output is `dist/<your-roll-number>_A2.zip`. This is the ZIP to submit. Do not submit `PROVISIONAL_A2.zip` as your final work. To reproduce the checked-in demonstration outputs deliberately, use `python prepare_submission.py --provisional`.

If you downloaded the ZIP while the remote repository was still empty, see [docs/github_upload.md](docs/github_upload.md) for the exact Git commands to publish from your computer.

The updated captioned demonstration has been uploaded to [Google Drive](https://drive.google.com/file/d/1RrtKoboo80VVcFxFKobq5ezko-mzP_3B/view?usp=drivesdk). Grant your instructor viewing access before submitting this link with the ZIP. The link is also saved in `docs/video_link.txt`. See [docs/demo_guide.md](docs/demo_guide.md) for the exact demonstration steps. A generated video of actual program-output excerpts is also included as `docs/demo.mp4`; it uses seed 0611 and shows actual execution excerpts with captions. It has no narration and is not a recording of you presenting. The assignment sheet does not specify a deadline.

## files

| file | purpose |
| --- | --- |
| `simulator.py` | channel, checksum, sender, receiver and timers for both protocols |
| `prepare_submission.py` | experiments, figures, report and ZIP generation |
| `record_demo.py` | optional captioned-video generation from actual stdout; needs ffmpeg |
| `test_simulator.py` | protocol and corruption checks |
| `results/report.pdf` | four-page report covering Tasks 1-5 |
| `results/results.csv` | the six experimental runs, including ACK and fault counts |
| `results/results.json` | exact configuration and metrics for every run |
| `results/gbn_vs_sr.png` | labelled GBN/SR comparison graph |
| `results/sr_ambiguity.png` | the Task 5 unsafe-window diagram |
| `results/task2_*_trace.csv` | compact Task 2 trace tables |
| `results/logs/` | full event logs for experiments and Task 2 |
| `docs/solution_notes.md` | readable task answers and viva notes |
| `docs/demo_guide.md` | video, submission and live demonstration guide |

## parameters

| option | meaning | default |
| --- | --- | --- |
| `--protocol gbn` / `sr` | transport protocol | sr |
| `--packets` | number of application messages | 200 |
| `--window` | sender window; SR receiver window too | 4 |
| `--bits` | sequence bits; numbers wrap modulo `2**bits` | 3 |
| `--seed` | last four roll-number digits, interpreted as an integer | required |
| `--loss` | loss probability for every data/ACK attempt | 0 |
| `--corruption` | corruption probability for every surviving data/ACK attempt | 0 |
| `--delay` | extra-delay probability for every surviving data/ACK attempt | 0 |
| `--timeout` | timeout in simulated seconds | 1.0 |
| `--extra-delay` | extra delay when selected, in seconds | 0.35 |
| `--rate` | bit rate in each direction | 2000000 |
| `--rtt` | base round-trip propagation time, in seconds | 0.5 |
| `--log` | optional path for the full event log | none |
| `--json` | optional metrics/configuration output path | none |
| `--quiet` | suppress console events; preserve summary and file logs | off |
| `--max-events` | stop a non-completing run after this many events | 2000000 |
| `--drop-packet-2` | deterministic first-attempt loss of packet 2 | off |

For k=3, GBN allows N=1..7 and SR allows N=1..4. Unsafe windows are rejected. Fault probabilities are independent; loss takes precedence because a lost frame never arrives to be checked or delayed. All attempted transmissions consume link serialization time.

## task 2 demonstration

```powershell
.\.venv\Scripts\python.exe simulator.py --protocol gbn --packets 10 --window 4 --bits 4 --timeout 1.5 --seed 0611 --drop-packet-2
.\.venv\Scripts\python.exe simulator.py --protocol sr --packets 10 --window 4 --bits 4 --timeout 1.5 --seed 0611 --drop-packet-2
```

These deterministic runs retransmit 4 data packets in GBN and 1 in SR. The eager sender sends 4 after ACK0 and 5 after ACK1, leaving 2-5 outstanding at the GBN timeout. Task 2 uses a 1.5-second timeout so the later ACKs return before packet 2 times out. The task's packet labels are 0-9 without sequence reuse, so its executable trace uses k=4; the required 200-packet experiments use k=3 and a 1-second timeout.

## model notes

- Events advance a simulated clock; a 60-second transfer need not take 60 wall-clock seconds.
- Data frames are exactly 1000 bytes: checksum 2, type 1, sequence 4, payload 993. The configured k limits the values in the sequence field, independently of its storage width. ACKs are 7 bytes.
- The channel models full duplex, per-direction transmission serialization and 250 ms base one-way propagation.
- The channel is FIFO per direction. A delayed packet can hold up later arrivals. This is a stated queued-link assumption, not an implementation of arbitrary packet reordering. Without a bound on old packet lifetime, k-bit textbook windows alone cannot protect against indefinitely stale traffic after repeated wraparound.
- `base`, `nextseqnum`, `expectedseqnum` and `rcv_base` are absolute local counters for readable bookkeeping. Frames carry only modulo sequence values. No protocol decision reads an absolute identity from application data; payload identities are checked only after completion as a correctness oracle.
- A cumulative GBN ACK x means all packets through x arrived in order. SR ACK x confirms only x. Corrupted GBN data causes a repeat of the last cumulative ACK; corrupted SR data/ACKs are discarded and recovered through timers.
- A version number invalidates an old timer event. GBN has one active logical timer; SR has one for each unacknowledged packet. Old heap entries cannot trigger an extra retry after an ACK cancels their timer.
- Metrics count data attempts separately from ACK attempts. Completion includes the final ACK. Throughput is unique delivered data-frame bits per simulated second (`delivered * 8000 / time`); actual application-byte goodput uses 993 bytes instead of 1000.
- A/B/C reset the same seed for each protocol. They have the same fault probabilities, but differing send histories consume the random stream differently. Single seeded runs are not statistical averages.

## submission checklist

- [x] Regenerated with roll number 0611; see `results/seed_status.txt`.
- [ ] Open the report and confirm it is at most four pages.
- [ ] Run both protocols and understand the timeout, ACK and buffer logs.
- [ ] Submit the correctly named ZIP from `dist/`.
- [ ] Record the working video using your final seed, upload it to Drive, verify viewing access and include its link.
- [ ] Follow the course's rules for outside assistance and authorship.
