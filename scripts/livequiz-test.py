#!/usr/bin/env python3
"""
End-to-end έλεγχος του Live Quiz (/live-quiz/) μέσω Nginx (θύρα 80).

Προσομοιώνει έναν καθηγητή (login, δημιουργία κουίζ, έναρξη, ροή ερωτήσεων)
και δύο μαθητές (είσοδος με PIN, WebSocket, απαντήσεις, πόντοι, κατάταξη),
ελέγχοντας και την εισαγωγή JSON/CSV. Χωρίς εξαρτήσεις εκτός του venv
(websocket-client). Εκτέλεση:
    /opt/school-portal/venv/bin/python /opt/school-portal/scripts/livequiz-test.py
"""
import json
import sys
import time
import urllib.request

from websocket import create_connection

sys.path.insert(0, "/opt/school-portal/scripts")
from lib import TEACHER_CODE, Client as HTTPClient, check, finish, ws_recv

BASE = "http://127.0.0.1/live-quiz/"
WS_BASE = "ws://127.0.0.1/live-quiz/ws/"


class Client(HTTPClient):
    def __init__(self):
        super().__init__(BASE)


def main():
    teacher = Client()

    print("[1] Σελίδες & αυθεντικοποίηση")
    with urllib.request.urlopen(BASE, timeout=10) as r:
        check("GET /live-quiz/ → 200", r.status == 200)
    code, _ = teacher.call("api/teacher/quizzes")
    check("API χωρίς login → 401", code == 401)
    code, _ = teacher.call("api/teacher/login", {"password": "λάθος"})
    check("Λάθος κωδικός → 401", code == 401)
    code, _ = teacher.call("api/teacher/login", {"password": TEACHER_CODE})
    check("Σωστός κωδικός → 200 + cookie", code == 200 and teacher.cookie("livequiz_teacher"))

    print("[2] Δημιουργία κουίζ & εισαγωγές")
    quiz = {"title": "Αυτοματοποιημένος Έλεγχος", "questions": [
        {"text": "2+2;", "options": ["3", "4", "5", "6"], "correct": 1, "time": 5},
        {"text": "Πρωτεύουσα της Ελλάδας;", "options": ["Θεσσαλονίκη", "Πάτρα", "Αθήνα", "Ηράκλειο"],
         "correct": 2, "time": 5},
    ]}
    code, data = teacher.call("api/teacher/quizzes", quiz)
    check("Δημιουργία κουίζ", code == 200 and "id" in data)
    quiz_id = data["id"]
    code, data = teacher.call("api/teacher/import", {
        "filename": "test.csv",
        "content": "text,option1,option2,option3,option4,correct,time\n1+1;,1,2,3,4,2,10\n"})
    check("Εισαγωγή CSV (correct 1-4)", code == 200 and data.get("count") == 1)
    csv_quiz = data.get("id")
    code, data = teacher.call("api/teacher/import", {
        "filename": "test.json", "content": json.dumps([quiz["questions"][0]])})
    check("Εισαγωγή JSON λίστας", code == 200 and data.get("count") == 1)
    json_quiz = data.get("id")
    code, data = teacher.call("api/teacher/samples/0", {})
    check("Έτοιμο ελληνικό παράδειγμα", code == 200 and "id" in data)
    sample_quiz = data.get("id")

    print("[3] Έναρξη live session & είσοδος μαθητών")
    code, data = teacher.call("api/teacher/start", {"quiz_id": quiz_id})
    pin = data.get("pin", "")
    check(f"PIN 4 ψηφίων ({pin})", code == 200 and len(pin) == 4 and pin.isdigit())
    tcookie = teacher.cookie("livequiz_teacher")
    tws = create_connection(WS_BASE + pin, timeout=15,
                            header=[f"Cookie: livequiz_teacher={tcookie}"])
    lobby = ws_recv(tws, {"lobby"})
    check("Προτζέκτορας βλέπει lobby", lobby["pin"] == pin)

    students = []
    for name in ("Μαρία", "Γιώργος"):
        s = Client()
        code, data = s.call("api/join", {"pin": pin, "name": name})
        check(f"Είσοδος «{name}»", code == 200 and data["name"] == name)
        sws = create_connection(WS_BASE + pin + "?token=" + data["token"], timeout=15)
        ws_recv(sws, {"lobby"})
        students.append((s, sws, data))
    # Κάθε είσοδος κάνει broadcast το lobby· διαβάζουμε μέχρι να εμφανιστούν και οι 2
    end = time.time() + 10
    names = set()
    while time.time() < end and names != {"Μαρία", "Γιώργος"}:
        lobby = ws_recv(tws, {"lobby"})
        names = set(lobby["players"])
    check("Live ονόματα στον προτζέκτορα", names == {"Μαρία", "Γιώργος"})

    print("[4] Ροή παιχνιδιού — ερώτηση 1 (σωστή vs λάθος απάντηση)")
    code, _ = teacher.call(f"api/teacher/{pin}/next", {})
    check("Έναρξη ερώτησης 1", code == 200)
    q_t = ws_recv(tws, {"question"})
    check("Καθηγητής βλέπει τη σωστή απάντηση", q_t.get("correct") == 1)
    q_s = ws_recv(students[0][1], {"question"})
    check("Μαθητής ΔΕΝ βλέπει τη σωστή απάντηση", "correct" not in q_s)
    students[0][1].send(json.dumps({"type": "answer", "choice": 1}))   # σωστά, γρήγορα
    ack = ws_recv(students[0][1], {"answer_ack"})
    check("Άμεση ανατροφοδότηση: σωστά + πόντοι", ack["correct"] and 900 <= ack["points"] <= 1000)
    students[1][1].send(json.dumps({"type": "answer", "choice": 0}))   # λάθος
    ack2 = ws_recv(students[1][1], {"answer_ack"})
    check("Λάθος απάντηση → 0 πόντοι", not ack2["correct"] and ack2["points"] == 0)
    students[0][1].send(json.dumps({"type": "answer", "choice": 2}))   # διπλοϋποβολή
    err = ws_recv(students[0][1], {"error"})
    check("Διπλή απάντηση απορρίπτεται", "ήδη" in err["message"])
    reveal = ws_recv(tws, {"reveal"}, timeout=10)   # όλοι απάντησαν → αυτόματο reveal
    check("Γράφημα απαντήσεων counts=[1,1,0,0]", reveal["counts"] == [1, 1, 0, 0])
    res = ws_recv(students[0][1], {"result"})
    check("Μαθητής βλέπει θέση Νο1", res["rank"] == 1 and res["score"] >= 900)
    board = ws_recv(tws, {"leaderboard"}, timeout=15)   # αυτόματο Top-5 μετά το reveal
    check("Top-5 leaderboard (Μαρία πρώτη)", board["top5"][0]["name"] == "Μαρία")

    print("[5] Ερώτηση 2 → τέλος & αποτελέσματα")
    code, _ = teacher.call(f"api/teacher/{pin}/next", {})
    check("Έναρξη ερώτησης 2", code == 200)
    ws_recv(tws, {"question"})
    for _, sws, _d in students:
        ws_recv(sws, {"question"})
        sws.send(json.dumps({"type": "answer", "choice": 2}))
        ws_recv(sws, {"answer_ack"})
    ws_recv(tws, {"reveal"}, timeout=10)
    ws_recv(tws, {"leaderboard"}, timeout=15)
    code, _ = teacher.call(f"api/teacher/{pin}/next", {})
    check("Τελικά αποτελέσματα", code == 200)
    fin = ws_recv(tws, {"finished"})
    check("Νικητής η Μαρία", fin["final"][0]["name"] == "Μαρία")
    fin_s = ws_recv(students[1][1], {"finished"})
    check("Μαθητής βλέπει τελική κατάταξη", len(fin_s["final"]) == 2)
    code, data = teacher.call(f"api/teacher/{pin}/results")
    check("API αποτελεσμάτων για CSV", code == 200 and len(data["board"]) == 2)
    code, _ = students[0][0].call("api/join", {"pin": pin, "name": "Αργός"})
    check("Είσοδος σε τελειωμένο παιχνίδι → 409", code == 409)

    print("[6] Καθαρισμός δεδομένων ελέγχου")
    for _, sws, _d in students:
        sws.close()
    tws.close()
    for qid in (quiz_id, csv_quiz, json_quiz, sample_quiz):
        teacher.call(f"api/teacher/quizzes/{qid}", method="DELETE")
    code, data = teacher.call("api/teacher/quizzes")
    check("Τα κουίζ ελέγχου διαγράφηκαν", code == 200 and not any(
        q["title"] == "Αυτοματοποιημένος Έλεγχος" for q in data["quizzes"]))

    finish("✓ Όλοι οι έλεγχοι του Live Quiz πέρασαν!")


if __name__ == "__main__":
    main()
