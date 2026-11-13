#!/usr/bin/env python3
"""紙面画像（paper.png / paper_s.png）が無い号だけ描く。GitHub Actions から呼ぶ。"""
import glob, os, shutil, subprocess, sys, tempfile
here = os.path.dirname(os.path.abspath(__file__))
root = os.path.dirname(here)
done = 0
for issue in sorted(glob.glob(os.path.join(root, "rn-*", "[0-9]" * 8, "issue.json"))):
    d = os.path.dirname(issue)
    if os.path.isfile(os.path.join(d, "paper.png")) and os.path.isfile(os.path.join(d, "paper_s.png")):
        continue
    out = tempfile.mkdtemp()
    subprocess.run([sys.executable, os.path.join(here, "news_paper.py"), issue, "--out", out,
                    "--slug", "x", "--no-fetch"], check=True)
    day = os.path.basename(d)
    for fn in ("paper.png", "paper_s.png"):
        shutil.copy(os.path.join(out, "x", day, fn), os.path.join(d, fn))
    done += 1
    print("rendered", d)
print("rendered issues:", done)
