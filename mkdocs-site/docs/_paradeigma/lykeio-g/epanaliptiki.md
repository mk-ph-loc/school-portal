# Επανάληψη Ύλης — Γ' Λυκείου

Συνοπτική επανάληψη με έμφαση στις **συχνές παγίδες**.

## 1. Δομές επιλογής

```python
# Πολλαπλή επιλογή με elif
vathmos = float(input("Βαθμός: "))

if vathmos < 0 or vathmos > 10:
    print("Μη έγκυρος βαθμός")
elif vathmos >= 9.5:
    print("Άριστα")
elif vathmos >= 7:
    print("Πολύ καλά")
elif vathmos >= 5:
    print("Καλώς")
else:
    print("Ανεπαρκώς")
```

!!! danger "Παγίδα #1: σειρά των ελέγχων"
    Αν βάλεις πρώτα το `vathmos >= 5`, θα «πιάσει» και τα άριστα! Οι έλεγχοι πρέπει να είναι από το **ειδικότερο στο γενικότερο**.

## 2. Εμφωλευμένες δομές & λογικοί τελεστές

```python
def einai_leap(year):
    """Σωστός έλεγχος δίσεκτου έτους."""
    return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)

for etos in [1900, 2000, 2024, 2023]:
    print(etos, "->", "δίσεκτο" if einai_leap(etos) else "κανονικό")
```

## 3. Βρόχοι — off-by-one

```python
# ΣΩΣΤΟ: άθροισμα 1..10
s = 0
for i in range(1, 11):     # το 11 ΔΕΝ συμπεριλαμβάνεται
    s += i
print("Άθροισμα 1..10 =", s)

# Αντίστροφη μέτρηση
for i in range(10, 0, -1):
    print(i, end=" ")
print()
```

!!! danger "Παγίδα #2: range"
    `range(n)` → `0..n-1` · `range(1, n)` → `1..n-1` · `range(1, n+1)` → `1..n`

## 4. Πίνακες — δείκτες

```python
pinakas = [10, 20, 30, 40, 50]

print("Πρώτο:", pinakas[0])
print("Τελευταίο:", pinakas[-1])
print("Τελευταίο (κλασικά):", pinakas[len(pinakas) - 1])

# Ασφαλής διάσχιση
for i in range(len(pinakas)):
    print("Θέση", i, "=", pinakas[i])
```

## 5. Συναρτήσεις & εμβέλεια

```python
metritis = 0          # καθολική

def auxisi():
    global metritis   # χρειάζεται για τροποποίηση
    metritis += 1

auxisi()
auxisi()
print("Μετρητής:", metritis)
```

## 6. Αλγόριθμοι-κλειδιά

```python
# Μέγιστος χωρίς max()
def megistos(lista):
    m = lista[0]
    for x in lista[1:]:
        if x > m:
            m = x
    return m

# Αντιστροφή συμβολοσειράς
def antistrofi(s):
    apotelesma = ""
    for ch in s:
        apotelesma = ch + apotelesma
    return apotelesma

# Παλίνδρομο
def palindromo(s):
    katharo = "".join(c.lower() for c in s if c.isalnum())
    return katharo == katharo[::-1]

print(megistos([3, 42, 7, 19]))
print(antistrofi("Πληροφορική"))
print(palindromo("A man a plan a canal Panama"))
```

## 7. Έλεγχος εγκυρότητας εισόδου

```python
def diavase_vathmo():
    while True:
        try:
            v = float(input("Δώσε βαθμό (0-10): "))
            if 0 <= v <= 10:
                return v
            print("Εκτός ορίων. Προσπάθησε ξανά.")
        except ValueError:
            print("Μη έγκυρη τιμή. Δώσε αριθμό.")

# print(diavase_vathmo())
print("Η συνάρτηση είναι έτοιμη για χρήση.")
```

## ✅ Checklist πριν τις εξετάσεις

- [ ] Κατανοώ τη διαφορά `//` και `/`
- [ ] Ξέρω ότι το `range` δεν περιλαμβάνει το άνω όριο
- [ ] Θυμάμαι ότι η `input()` επιστρέφει `str`
- [ ] Ελέγχω τα όρια των πινάκων (off-by-one)
- [ ] Χρησιμοποιώ σωστή σειρά σε `if/elif`
- [ ] Τεκμηριώνω τον κώδικά μου με σχόλια