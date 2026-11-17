# Δομές Δεδομένων

Η επιλογή της σωστής δομής δεδομένων καθορίζει την αποδοτικότητα του προγράμματος.

## Στοίβα (Stack) — LIFO

**Last In, First Out**: το τελευταίο που μπαίνει βγαίνει πρώτο.

```python
class Stoiva:
    def __init__(self):
        self._dedomena = []

    def push(self, x):
        self._dedomena.append(x)

    def pop(self):
        if self.is_empty():
            raise IndexError("Η στοίβα είναι άδεια")
        return self._dedomena.pop()

    def peek(self):
        return self._dedomena[-1] if self._dedomena else None

    def is_empty(self):
        return len(self._dedomena) == 0

s = Stoiva()
s.push("Α")
s.push("Β")
s.push("Γ")
print("Κορυφή:", s.peek())
print("Εξαγωγή:", s.pop())
print("Εξαγωγή:", s.pop())
```

**Εφαρμογή:** έλεγχος ισορροπίας παρενθέσεων.

```python
def isorropia_parentheseon(keimeno):
    stoiva = []
    zeugaria = {')': '(', ']': '[', '}': '{'}
    for ch in keimeno:
        if ch in "([{":
            stoiva.append(ch)
        elif ch in ")]}":
            if not stoiva or stoiva.pop() != zeugaria[ch]:
                return False
    return len(stoiva) == 0

print(isorropia_parentheseon("(a + b) * [c - d]"))
print(isorropia_parentheseon("(a + b]"))
```

## Ουρά (Queue) — FIFO

**First In, First Out**: όποιος μπει πρώτος, εξυπηρετείται πρώτος.

```python
from collections import deque

oura = deque()
oura.append("Μαρία")     # enqueue
oura.append("Γιώργος")
oura.append("Ελένη")

print("Εξυπηρέτηση:", oura.popleft())   # dequeue
print("Εξυπηρέτηση:", oura.popleft())
print("Αναμονή:", list(oura))
```

## Λεξικό (Dictionary) — κλειδί → τιμή

```python
mathites = {
    "ΑΜ001": {"onoma": "Μαρία", "vathmos": 9.5},
    "ΑΜ002": {"onoma": "Γιώργος", "vathmos": 8.0},
    "ΑΜ003": {"onoma": "Ελένη", "vathmos": 10.0}
}

print("Όνομα ΑΜ002:", mathites["ΑΜ002"]["onoma"])

for am, stoicheia in mathites.items():
    print(am, "-", stoicheia["onoma"], ":", stoicheia["vathmos"])

# Μέσος όρος τάξης
mo = sum(m["vathmos"] for m in mathites.values()) / len(mathites)
print("Μ.Ο. τάξης:", round(mo, 2))
```

## Σύνολο (Set)

```python
tmima_a = {"Μαρία", "Γιώργος", "Ελένη", "Νίκος"}
tmima_b = {"Ελένη", "Νίκος", "Άννα"}

print("Ένωση:", tmima_a | tmima_b)
print("Τομή:", tmima_a & tmima_b)
print("Διαφορά:", tmima_a - tmima_b)
```

## Σύγκριση δομών

| Δομή | Πρόσβαση | Εισαγωγή | Διαγραφή | Χρήση |
| --- | --- | --- | --- | --- |
| Λίστα | O(1) με δείκτη | O(1) στο τέλος | O(n) | Γενική συλλογή |
| Στοίβα | O(1) κορυφή | O(1) | O(1) | Undo, αναδρομή |
| Ουρά | O(1) άκρα | O(1) | O(1) | Σειρές αναμονής |
| Λεξικό | O(1) με κλειδί | O(1) | O(1) | Αναζήτηση με κλειδί |
| Σύνολο | O(1) έλεγχος | O(1) | O(1) | Μοναδικές τιμές |

## Ασκήσεις

1. Υλοποίησε ουρά με δύο στοίβες.
2. Μέτρησε τη συχνότητα εμφάνισης λέξεων σε ένα κείμενο με λεξικό.
3. Βρες τα κοινά στοιχεία δύο λιστών χρησιμοποιώντας σύνολα.