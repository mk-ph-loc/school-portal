# Λύσεις Ασκήσεων

Πλήρεις λύσεις με επεξηγήσεις και παιδαγωγικές σημειώσεις για κάθε τάξη.

## Α' Γυμνασίου

### Εισαγωγή στην Πληροφορική

**Άσκηση 2:** Πόσα Bytes είναι τα 2 KB;

```python
kb = 2
bytes_olika = kb * 1024
print("2 KB =", bytes_olika, "Bytes")
```

**Απάντηση:** 2 × 1024 = **2048 Bytes**.

!!! note "Παιδαγωγική σημείωση"
    Τονίστε ότι χρησιμοποιούμε 1024 (2¹⁰) και όχι 1000, γιατί οι υπολογιστές λειτουργούν στο δυαδικό σύστημα.

### Python

**Άσκηση 1:** Εμβαδόν ορθογωνίου.

```python
mikos = float(input("Μήκος: "))
platos = float(input("Πλάτος: "))
emvadon = mikos * platos
print("Εμβαδόν:", emvadon)
```

**Άσκηση 2:** Κελσίου → Φαρενάιτ.

```python
celsius = float(input("Βαθμοί Κελσίου: "))
fahrenheit = celsius * 9 / 5 + 32
print("Φαρενάιτ:", fahrenheit)
```

**Άσκηση 3:** Άρτιοι από 2 έως 20.

```python
for i in range(2, 21, 2):
    print(i, end=" ")
print()

# Εναλλακτικά με έλεγχο
for i in range(2, 21):
    if i % 2 == 0:
        print(i, end=" ")
print()
```

## Β' Γυμνασίου

### Δομές Επανάληψης

**Άσκηση 1:** Παραγοντικό του 5.

```python
n = 5
paragontiko = 1
for i in range(1, n + 1):
    paragontiko *= i
print(str(n) + "! =", paragontiko)
```

**Άσκηση 3:** Άθροισμα μέχρι το 0.

```python
athroisma = 0
while True:
    x = int(input("Αριθμός (0 για τέλος): "))
    if x == 0:
        break
    athroisma += x
print("Άθροισμα:", athroisma)
```

### Δυαδικό Σύστημα

| Άσκηση | Απάντηση | Επεξήγηση |
| --- | --- | --- |
| `10110₂` → δεκαδικό | **22** | 16 + 0 + 4 + 2 + 0 |
| `25₁₀` → δυαδικό | **11001** | 16 + 8 + 1 |
| Διαφορετικοί αριθμοί με 4 bits | **16** | 2⁴ = 16 (0 έως 15) |
| Μέγιστος σε 1 Byte | **255** | 2⁸ − 1 |

```python
print(int("10110", 2))      # 22
print(bin(25)[2:])          # 11001
print(2 ** 4)               # 16
print(2 ** 8 - 1)           # 255
```

## Γ' Γυμνασίου

### Πίνακες

**Άσκηση 2:** Θέση μεγαλύτερου στοιχείου.

```python
def thesi_megistou(lista):
    thesi = 0
    for i in range(1, len(lista)):
        if lista[i] > lista[thesi]:
            thesi = i
    return thesi

data = [12, 45, 7, 89, 23]
print("Θέση:", thesi_megistou(data), "- Τιμή:", data[thesi_megistou(data)])
```

**Άσκηση 3:** Αντιστροφή πίνακα χωρίς έτοιμη συνάρτηση.

```python
def antistrofi(lista):
    a = lista[:]
    arxi, telos = 0, len(a) - 1
    while arxi < telos:
        a[arxi], a[telos] = a[telos], a[arxi]
        arxi += 1
        telos -= 1
    return a

print(antistrofi([1, 2, 3, 4, 5]))
```

### Συναρτήσεις

**Άσκηση 3:** Αναδρομικό άθροισμα 1..n.

```python
def athroisma_n(n):
    if n <= 0:
        return 0
    return n + athroisma_n(n - 1)

print(athroisma_n(10))   # 55
```

## Α' Λυκείου

### Αλγοριθμική

**Άσκηση 3:** Παράδειγμα όπου η άπληστη μέθοδος αποτυγχάνει.

Με κέρματα `[1, 3, 4]` και στόχο `6`:
- **Άπληστη:** 4 + 1 + 1 = **3 κέρματα**
- **Βέλτιστη:** 3 + 3 = **2 κέρματα**

```python
def aplisti(poso, kermata):
    plithos = 0
    for k in sorted(kermata, reverse=True):
        plithos += poso // k
        poso %= k
    return plithos

print("Άπληστη λύση:", aplisti(6, [1, 3, 4]), "κέρματα")
print("Βέλτιστη: 2 κέρματα (3+3)")
```

## Β' & Γ' Λυκείου

Οι λύσεις των σύνθετων θεμάτων συνοδεύονται από πίνακες τιμών (trace tables) και ανάλυση πολυπλοκότητας.

!!! tip "Συμβουλή διδασκαλίας"
    Ζητήστε από τους μαθητές να συμπληρώσουν **πίνακα τιμών** πριν γράψουν κώδικα. Εντοπίζει τα off-by-one σφάλματα νωρίς.