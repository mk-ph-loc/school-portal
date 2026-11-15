# Αλγοριθμική

## Τα κριτήρια ενός αλγορίθμου

Ένας αλγόριθμος πρέπει να ικανοποιεί **πέντε** κριτήρια:

| Κριτήριο | Επεξήγηση |
| --- | --- |
| **Είσοδος** | Καθορισμένα δεδομένα εισόδου (ή καμία) |
| **Έξοδος** | Τουλάχιστον ένα αποτέλεσμα |
| **Καθοριστικότητα** | Κάθε εντολή είναι σαφής, χωρίς αμφισημία |
| **Περατότητα** | Τελειώνει μετά από πεπερασμένα βήματα |
| **Αποτελεσματικότητα** | Παράγει το σωστό αποτέλεσμα |

!!! failure "Παράδειγμα μη-αλγορίθμου"
    «Ανακάτεψε τα χαρτιά μέχρι να έρθουν στη σειρά» — δεν υπάρχει εγγύηση περατότητας.

## Στρατηγικές επίλυσης προβλημάτων

### 1. Διαίρει και Βασίλευε

Σπάμε το πρόβλημα σε μικρότερα, όμοια υποπροβλήματα.

```python
def dyadiki_anazitisi(lista, stoixeio):
    """Αναζήτηση σε ΤΑΞΙΝΟΜΗΜΕΝΗ λίστα — O(log n)."""
    arxi, telos = 0, len(lista) - 1
    while arxi <= telos:
        mesa = (arxi + telos) // 2
        if lista[mesa] == stoixeio:
            return mesa
        elif lista[mesa] < stoixeio:
            arxi = mesa + 1
        else:
            telos = mesa - 1
    return -1

dedomena = [3, 7, 12, 19, 25, 42, 58, 71]
print("Θέση του 25:", dyadiki_anazitisi(dedomena, 25))
print("Θέση του 100:", dyadiki_anazitisi(dedomena, 100))
```

### 2. Άπληστη μέθοδος (Greedy)

Σε κάθε βήμα επιλέγουμε το τοπικά καλύτερο.

```python
def resta(poso, kermata):
    """Επιστρέφει τα κέρματα για το ρέστο (άπληστη μέθοδος)."""
    apotelesma = {}
    for k in sorted(kermata, reverse=True):
        if poso >= k:
            plithos = poso // k
            apotelesma[k] = plithos
            poso = poso % k
    return apotelesma

print(resta(287, [200, 100, 50, 20, 10, 5, 2, 1]))
```

### 3. Οπισθοδρόμηση (Backtracking)

Δοκιμάζουμε λύσεις και «γυρίζουμε πίσω» όταν αποτυγχάνουν.

```python
def permutatseis(stoixeia):
    """Παράγει όλες τις μεταθέσεις μιας λίστας."""
    if len(stoixeia) <= 1:
        return [stoixeia]
    apotelesma = []
    for i in range(len(stoixeia)):
        ypoloipa = stoixeia[:i] + stoixeia[i+1:]
        for p in permutatseis(ypoloipa):
            apotelesma.append([stoixeia[i]] + p)
    return apotelesma

for p in permutatseis([1, 2, 3]):
    print(p)
```

## Ανάλυση πολυπλοκότητας (εισαγωγή)

| Συμβολισμός | Όνομα | Παράδειγμα |
| --- | --- | --- |
| O(1) | Σταθερή | Πρόσβαση σε στοιχείο πίνακα |
| O(log n) | Λογαριθμική | Δυαδική αναζήτηση |
| O(n) | Γραμμική | Σειριακή αναζήτηση |
| O(n log n) | Γραμμο-λογαριθμική | Συγχώνευση (merge sort) |
| O(n²) | Τετραγωνική | Ταξινόμηση φυσαλίδας |

```python
import time

def seiriaki(lista, x):
    for i in range(len(lista)):
        if lista[i] == x:
            return i
    return -1

data = list(range(100000))

t0 = time.perf_counter()
seiriaki(data, 99999)
t1 = time.perf_counter()
dyadiki_anazitisi(data, 99999)
t2 = time.perf_counter()

print("Σειριακή:", round((t1 - t0) * 1000, 3), "ms")
print("Δυαδική:", round((t2 - t1) * 1000, 3), "ms")
```

## Ασκήσεις

1. Εξήγησε γιατί η δυαδική αναζήτηση απαιτεί ταξινομημένη λίστα.
2. Υλοποίησε τη σειριακή αναζήτηση και σύγκρινε την απόδοση.
3. Δώσε παράδειγμα προβλήματος όπου η άπληστη μέθοδος **δεν** δίνει βέλτιστη λύση.