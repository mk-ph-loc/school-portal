# Ασκήσεις Python — Β' Γυμνασίου

Εφαρμογές με βρόχους, αθροιστές και μετρητές. Πάτησε **▶ Εκτέλεση** σε κάθε παράδειγμα!

## Άσκηση 1: Άθροισμα και Μέσος Όρος

```python
plithos = int(input("Πόσοι αριθμοί; "))
athroisma = 0

for i in range(plithos):
    x = float(input("Αριθμός " + str(i + 1) + ": "))
    athroisma = athroisma + x

if plithos > 0:
    print("Άθροισμα:", athroisma)
    print("Μέσος όρος:", round(athroisma / plithos, 2))
else:
    print("Δεν δόθηκαν αριθμοί.")
```

## Άσκηση 2: Μέγιστος αριθμός

```python
megisto = None

for i in range(5):
    x = int(input("Δώσε αριθμό: "))
    if megisto is None or x > megisto:
        megisto = x

print("Ο μεγαλύτερος είναι:", megisto)
```

## Άσκηση 3: Παραγοντικό

```python
n = int(input("Δώσε αριθμό (0-20): "))
paragontiko = 1

for i in range(1, n + 1):
    paragontiko = paragontiko * i

print(str(n) + "! =", paragontiko)
```

## Άσκηση 4: Πρώτος αριθμός

```python
n = int(input("Δώσε αριθμό: "))

if n < 2:
    print("Δεν είναι πρώτος")
else:
    einai_protos = True
    for d in range(2, int(n ** 0.5) + 1):
        if n % d == 0:
            einai_protos = False
            break
    if einai_protos:
        print("Είναι πρώτος ✓")
    else:
        print("Δεν είναι πρώτος ✗")
```

## Άσκηση 5: Μαντεψιά αριθμού

```python
import random

mystikos = random.randint(1, 20)
prospatheies = 0

while True:
    mantepsia = int(input("Μάντεψε (1-20): "))
    prospatheies = prospatheies + 1
    if mantepsia < mystikos:
        print("Μεγαλύτερος!")
    elif mantepsia > mystikos:
        print("Μικρότερος!")
    else:
        print("Σωστά! Προσπάθειες:", prospatheies)
        break
```

## Άσκηση 6: Τριγωνικός σχηματισμός

```python
grammes = 5
for i in range(1, grammes + 1):
    print("*" * i)
```

!!! tip "Δοκίμασε"
    Άλλαξε το `grammes` σε 8 και δες τι συμβαίνει!

## 🏆 Πρόκληση

Γράψε πρόγραμμα που εμφανίζει όλους τους **πρώτους αριθμούς** από το 2 έως το 50.