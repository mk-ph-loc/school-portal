# Πίνακες

Ένας **πίνακας** αποθηκεύει πολλές τιμές του ίδιου τύπου κάτω από ένα κοινό όνομα.

## Μονοδιάστατος πίνακας

```glossa
ΑΛΓΟΡΙΘΜΟΣ Βαθμοί
ΜΕΤΑΒΛΗΤΕΣ
  ΑΚΕΡΑΙΕΣ: i
  ΠΡΑΓΜΑΤΙΚΕΣ: Β[5]
ΑΡΧΗ
  ΓΙΑ i ΑΠΟ 1 ΜΕΧΡΙ 5
    ΔΙΑΒΑΣΕ Β[i]
  ΤΕΛΟΣ_ΕΠΑΝΑΛΗΨΗΣ
  ΓΡΑΨΕ 'Ο πρώτος βαθμός: ', Β[1]
ΤΕΛΟΣ_ΠΡΟΓΡΑΜΜΑΤΟΣ
```

!!! warning "Δείκτες: προσοχή!"
    Στην ψευδογλώσσα οι δείκτες ξεκινούν από **1**, ενώ στην Python από **0**.

Σε Python χρησιμοποιούμε **λίστες**:

```python
vathmoi = [8.5, 9.0, 7.5, 10.0, 6.5]

print("Πρώτος βαθμός:", vathmoi[0])
print("Τελευταίος:", vathmoi[-1])
print("Πλήθος:", len(vathmoi))
```

## Διάσχιση πίνακα

```python
vathmoi = [8.5, 9.0, 7.5, 10.0, 6.5]

# Άθροισμα και μέσος όρος
athroisma = 0
for v in vathmoi:
    athroisma = athroisma + v

print("Άθροισμα:", athroisma)
print("Μέσος όρος:", round(athroisma / len(vathmoi), 2))

# Μέγιστος και ελάχιστος
print("Μέγιστος:", max(vathmoi))
print("Ελάχιστος:", min(vathmoi))
```

## Αναζήτηση στοιχείου

```python
onomata = ["Μαρία", "Γιώργος", "Ελένη", "Νίκος"]
anazitisi = input("Ποιο όνομα ψάχνεις; ")

vrethike = False
for i in range(len(onomata)):
    if onomata[i] == anazitisi:
        print("Βρέθηκε στη θέση", i)
        vrethike = True
        break

if not vrethike:
    print("Δεν βρέθηκε")
```

## Δισδιάστατος πίνακας

```python
# 3 μαθητές × 3 μαθήματα
vathmologia = [
    [8, 9, 7],
    [10, 9, 10],
    [6, 7, 8]
]

for i in range(len(vathmologia)):
    mo = sum(vathmologia[i]) / len(vathmologia[i])
    print("Μαθητής", i + 1, "- Μ.Ο.:", round(mo, 2))
```

## Ταξινόμηση (φυσαλίδα)

```python
arithmoi = [42, 7, 19, 3, 25]
print("Πριν:", arithmoi)

n = len(arithmoi)
for i in range(n - 1):
    for j in range(n - 1 - i):
        if arithmoi[j] > arithmoi[j + 1]:
            arithmoi[j], arithmoi[j + 1] = arithmoi[j + 1], arithmoi[j]

print("Μετά:", arithmoi)
```

## Ασκήσεις

1. Διάβασε 10 αριθμούς σε πίνακα και εμφάνισε μόνο τους άρτιους.
2. Βρες τη θέση του μεγαλύτερου στοιχείου ενός πίνακα.
3. Αντίστρεψε τη σειρά των στοιχείων ενός πίνακα χωρίς έτοιμη συνάρτηση.