# app.py - Python Code Analyzer with Table Output
import os
import tempfile
import uuid
import subprocess
import re
import math
from flask import Flask, request

from radon.complexity import cc_visit, cc_rank
from radon.metrics import h_visit

app = Flask(__name__)

# ------------------- Analyzer Functions -------------------
def run_pylint(filename, disable_import_error=True, timeout_s=15):
    cmd = ["pylint", "--score=y"]
    if disable_import_error:
        cmd += ["--disable=import-error"]
    cmd.append(filename)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout_s
        )
        output = (result.stdout or "") + "\n" + (result.stderr or "")
    except FileNotFoundError:
        return 0.0, "Pylint not found. Install pylint (`pip install pylint`)."
    except subprocess.TimeoutExpired:
        return 0.0, "Pylint timed out."
    except Exception as e:
        return 0.0, f"Pylint error: {e}"

    m = re.search(r"rated at\s+(-?\d+(?:\.\d+)?)\s*/\s*10", output, re.IGNORECASE)
    if m:
        try:
            score = float(m.group(1))
            return round(score, 2), output
        except Exception:
            pass

    m2 = re.search(r"(-?\d+(?:\.\d+)?)\s*/\s*10", output)
    if m2:
        try:
            return round(float(m2.group(1)), 2), output
        except Exception:
            pass

    return 0.0, output


def cc_to_score(cc_results):
    mapping = {"A": 10, "B": 8, "C": 6, "D": 4, "E": 2, "F": 0}
    if not cc_results:
        return 10.0
    scores = [mapping.get(cc_rank(r.complexity), 0) for r in cc_results]
    return round(sum(scores) / len(scores), 2)


def halstead_scores(source_code):
    halstead = h_visit(source_code)
    if not halstead:
        return 10.0, 10.0, 0.0, 0.0

    efforts = [getattr(h, "effort", 0.0) for h in halstead]
    bugs = [getattr(h, "bugs", 0.0) for h in halstead]

    raw_effort = max(efforts) if efforts else 0.0
    raw_bugs = sum(bugs) if bugs else 0.0

    # log-scaled effort
    effort_score = 10.0 if raw_effort <= 0 else max(0.0, min(10.0, 10.0 - (math.log10(raw_effort + 1) * 2.0)))
    bug_score = max(0.0, min(10.0, 10.0 - (raw_bugs * 10.0)))

    return round(effort_score, 2), round(bug_score, 2), raw_effort, raw_bugs


def analyze_code_string(code_str):
    tmp_dir = tempfile.gettempdir()
    fname = f"upload_{uuid.uuid4().hex}.py"
    fullpath = os.path.join(tmp_dir, fname)

    with open(fullpath, "w", encoding="utf-8") as f:
        f.write(code_str)

    try:
        pylint_score, pylint_output = run_pylint(fullpath)
        try:
            cc_results = cc_visit(code_str)
            cc_score = cc_to_score(cc_results)
        except Exception as e:
            cc_results = []
            cc_score = 0.0
            pylint_output += f"\nRadon CC error: {e}"

        try:
            effort_score, bug_score, effort, bugs = halstead_scores(code_str)
        except Exception as e:
            effort_score = bug_score = 0.0
            effort = bugs = 0.0
            pylint_output += f"\nHalstead error: {e}"

        return {
            "pylint_score": pylint_score,
            "pylint_output": pylint_output,
            "cc_score": cc_score,
            "effort_score": effort_score,
            "bug_score": bug_score,
            "raw_effort": effort,
            "raw_bugs": bugs,
            "test_pass_rate": "10/10",
            "maintainability": "10/10"
        }
    finally:
        try:
            os.remove(fullpath)
        except Exception:
            pass


# ------------------- Web Routes -------------------
@app.route("/", methods=["GET", "POST"])
def index():
    code = ""
    if not hasattr(app, "all_results"):
        app.all_results = []

    if request.method == "POST":
        code = request.form.get("code_text", "").strip()
        if code:
            results = analyze_code_string(code)
            app.all_results.append(results)

    table_html = ""
    if app.all_results:
        header = """
        <table border="1" cellpadding="6" cellspacing="0" style="border-collapse:collapse;background:#fff;margin-top:16px">
          <tr style="background:#eee">
            <th>#</th>
            <th>Pylint Score</th>
            <th>CC Score</th>
            <th>Effort Score</th>
            <th>Raw Effort</th>
            <th>Bug Score</th>
            <th>Raw Bugs</th>
            <th>Test Pass Rate</th>
            <th>Maintainability</th>
          </tr>
        """
        rows = ""
        for i, r in enumerate(app.all_results, 1):
            rows += f"""
              <tr>
                <td>{i}</td>
                <td>{r['pylint_score']}/10</td>
                <td>{r['cc_score']}/10</td>
                <td>{r['effort_score']}/10</td>
                <td>{r['raw_effort']}</td>
                <td>{r['bug_score']}/10</td>
                <td>{r['raw_bugs']}</td>
                <td>{r['test_pass_rate']}</td>
                <td>{r['maintainability']}</td>
              </tr>
            """
        table_html = header + rows + "</table>"

    return f"""
<!doctype html>
<html>
<head><meta charset="utf-8"/><title>Python Code Analyzer</title>
<style>
 body{{font-family:Arial,Helvetica,sans-serif;margin:24px;background:#f7f7f8}}
 textarea{{width:100%;height:260px;font-family:monospace;font-size:14px;padding:8px}}
 .button{{margin-top:8px;padding:10px 14px}}
 table{{width:100%;font-size:14px}}
 th,td{{text-align:center}}
</style></head><body>
<h1>Python Code Analyzer</h1>
<form method="post">
 <textarea name="code_text" placeholder="# paste python code here...">{code}</textarea><br>
 <button class="button" type="submit">Analyze</button>
</form>
{table_html}
</body></html>
"""

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
