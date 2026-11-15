# Συναρτήσεις & Διαδικασίες

Ο **τμηματικός προγραμματισμός** χωρίζει ένα μεγάλο πρόγραμμα σε μικρά, επαναχρησιμοποιήσιμα κομμάτια.

## Γιατί συναρτήσεις;

- ♻️ **Επαναχρησιμοποίηση:** γράφεις μία φορά, χρησιμοποιείς πολλές.
- 🧩 **Οργάνωση:** κάθε τμήμα κάνει μία δουλειά.
- 🐛 **Ευκολότερος έλεγχος:** ελέγχεις κάθε κομμάτι ξεχωριστά.

## Δήλωση στην ψευδογλώσσα

```glossa
ΑΛΓΟΡΙΘΜΟΣ Παράδειγμα_Συνάρτησης
ΜΕΤΑΒΛΗΤΕΣ
  ΑΚΕΡΑΙΕΣ: x, y
ΑΡΧΗ
  ΔΙΑΒΑΣΕ x, y
  ΓΡΑΨΕ 'Άθροισμα: ', Άθροισμα(x, y)
ΤΕΛΟΣ_ΠΡΟΓΡΑΜΜΑΤΟΣ

ΣΥΝΑΡΤΗΣΗ Άθροισμα(α, β) : ΑΚΕΡΑΙΑ
ΑΡΧΗ
  ΕΠΙΣΤΡΕΦΕΙ α + β
ΤΕΛΟΣ_ΣΥΝΑΡΤΗΣΗΣ
```

## Συναρτήσεις στην Python

```python
def athroisma(a, b):
    """Επιστρέφει το άθροισμα δύο αριθμών."""
    return a + b

def mesos_oros(lista):
    """Επιστρέφει τον μέσο όρο μιας λίστας."""
    if len(lista) == 0:
        return 0
    return sum(lista) / len(lista)

print("Άθροισμα:", athroisma(7, 5))
print("Μ.Ο.:", mesos_oros([8, 9, 10, 7]))
```

## Παράμετροι με προεπιλεγμένες τιμές

```python
def chairetismos(onoma, prosfoni="Γεια σου"):
    print(prosfoni + ", " + onoma + "!")

chairetismos("Μαρία")
chairetismos("Γιώργο", "Καλημέρα")
```

## Πολλές επιστροφές

```python
def statistika(arithmoi):
    """Επιστρέφει ελάχιστο, μέγιστο και μέσο όρο."""
    return min(arithmoi), max(arithmoi), sum(arithmoi) / len(arithmoi)

data = [12, 7, 25, 3, 18]
elachisto, megisto, mo = statistika(data)

print("Ελάχιστο:", elachisto)
print("Μέγιστο:", megisto)
print("Μ.Ο.:", round(mo, 2))
```

## Αναδρομή

Μια συνάρτηση που καλεί τον εαυτό της:

```python
def paragontiko(n):
    if n <= 1:
        return 1
    return n * paragontiko(n - 1)

for i in range(6):
    print(str(i) + "! =", paragontiko(i))
```

!!! danger "Προσοχή στην αναδρομή"
    Χρειάζεται πάντα **συνθήκη τερματισμού**, αλλιώς η αναδρομή δεν τελειώνει ποτέ.

## Πλήρες παράδειγμα: Βαθμολογία τάξης

```python
def charaktirismos(mo):
    if mo >= 9.5:
        return "Άριστα"
    elif mo >= 7:
        return "Πολύ καλά"
    elif mo >= 5:
        return "Καλώς"
    return "Χρειάζεται βελτίωση"

def ektypose_anafora(onoma, vathmoi):
    mo = sum(vathmoi) / len(vathmoi)
    print(onoma + ": Μ.Ο. " + str(round(mo, 2)) + " — " + charaktirismos(mo))

ektypose_anafora("Μαρία", [10, 9, 10])
ektypose_anafora("Γιώργος", [7, 8, 6])
ektypose_anafora("Ελένη", [5, 6, 4])
```

## Ασκήσεις

1. Γράψε συνάρτηση `einai_artios(n)` που επιστρέφει `True`/`False`.
2. Γράψε συνάρτηση που μετατρέπει Κελσίου σε Φαρενάιτ.
3. Γράψε αναδρομική συνάρτηση για το άθροισμα `1 + 2 + ... + n`.