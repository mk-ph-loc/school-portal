# Πολυπλοκότητα Αλγορίθμων

Η **πολυπλοκότητα** περιγράφει πώς αυξάνεται ο χρόνος (ή η μνήμη) ενός αλγορίθμου καθώς μεγαλώνει το μέγεθος της εισόδου `n`.

## Συμβολισμός Big-O

| Συμβολισμός | Όνομα | n=10 | n=1.000 | n=1.000.000 |
| --- | --- | --- | --- | --- |
| O(1) | Σταθερή | 1 | 1 | 1 |
| O(log n) | Λογαριθμική | ~3 | ~10 | ~20 |
| O(n) | Γραμμική | 10 | 1.000 | 1.000.000 |
| O(n log n) | Γραμμο-λογαριθμική | ~33 | ~10.000 | ~20.000.000 |
| O(n²) | Τετραγωνική | 100 | 1.000.000 | 10¹² |
| O(2ⁿ) | Εκθετική | 1.024 | 🚫 | 🚫 |

!!! warning "Γιατί έχει σημασία"
    Ένας αλγόριθμος O(n²) σε 1 εκατομμύριο στοιχεία μπορεί να χρειαστεί **ώρες**, ενώ ένας O(n log n) **δευτερόλεπτα**.

## Παραδείγματα ανά κατηγορία

```python
# O(1) — σταθερή
def proto(lista):
    return lista[0] if lista else None

# O(n) — γραμμική
def athroisma(lista):
    s = 0
    for x in lista:
        s += x
    return s

# O(n²) — τετραγωνική
def zeugaria(lista):
    plithos = 0
    for i in range(len(lista)):
        for j in range(len(lista)):
            plithos += 1
    return plithos

# O(log n) — λογαριθμική
def misa(n):
    bimata = 0
    while n > 1:
        n //= 2
        bimata += 1
    return bimata

data = list(range(100))
print("O(1):", proto(data))
print("O(n):", athroisma(data))
print("O(n²):", zeugaria(data))
print("O(log n):", misa(1024))
```

## Πρακτική μέτρηση χρόνου

```python
import time

def metrise(synartisi, dedomena, epanalipseis=3):
    """Επιστρέφει τον μέσο χρόνο εκτέλεσης σε ms."""
    synolikos = 0
    for _ in range(epanalipseis):
        t0 = time.perf_counter()
        synartisi(dedomena)
        synolikos += time.perf_counter() - t0
    return round((synolikos / epanalipseis) * 1000, 3)

def bubble(lst):
    a = lst[:]
    for i in range(len(a) - 1):
        for j in range(len(a) - 1 - i):
            if a[j] > a[j+1]:
                a[j], a[j+1] = a[j+1], a[j]
    return a

for megethos in [100, 200, 400]:
    dedomena = list(range(megethos, 0, -1))
    print("n =", megethos, "->", metrise(bubble, dedomena), "ms")
```

!!! note "Τι θα παρατηρήσεις"
    Διπλασιάζοντας το `n`, ο χρόνος **τετραπλασιάζεται** — χαρακτηριστικό της O(n²).

## Πολυπλοκότητα χώρου

```python
# O(1) χώρος — μόνο μερικές μεταβλητές
def athroisma_choros(lista):
    s = 0
    for x in lista:
        s += x
    return s

# O(n) χώρος — δημιουργεί νέα λίστα
def diplasia(lista):
    return [x * 2 for x in lista]

print(athroisma_choros([1, 2, 3]))
print(diplasia([1, 2, 3]))
```

## Κανόνες απλοποίησης

1. Αγνοούμε τις σταθερές: `O(3n)` → `O(n)`
2. Κρατάμε τον κυρίαρχο όρο: `O(n² + n)` → `O(n²)`
3. Διαδοχικά βήματα **προστίθενται**, φωλιασμένα **πολλαπλασιάζονται**.

## Ασκήσεις

1. Βρες την πολυπλοκότητα του κώδικα: δύο διαδοχικοί βρόχοι `for` με `n` επαναλήψεις.
2. Γιατί η δυαδική αναζήτηση είναι O(log n);
3. Μέτρησε πρακτικά τη διαφορά μεταξύ `sorted()` και φυσαλίδας για n=2000.