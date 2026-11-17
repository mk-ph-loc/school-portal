# Αναζήτηση & Ταξινόμηση

## Αλγόριθμοι αναζήτησης

### Σειριακή αναζήτηση — O(n)

```python
def seiriaki(lista, x):
    """Ελέγχει κάθε στοιχείο με τη σειρά."""
    for i in range(len(lista)):
        if lista[i] == x:
            return i
    return -1

data = [42, 7, 19, 3, 25, 88]
print("Θέση του 19:", seiriaki(data, 19))
print("Θέση του 100:", seiriaki(data, 100))
```

### Δυαδική αναζήτηση — O(log n)

```python
def dyadiki(lista, x):
    """Απαιτεί ΤΑΞΙΝΟΜΗΜΕΝΗ λίστα."""
    lo, hi = 0, len(lista) - 1
    while lo <= hi:
        mid = (lo + hi) // 2
        if lista[mid] == x:
            return mid
        elif lista[mid] < x:
            lo = mid + 1
        else:
            hi = mid - 1
    return -1

taksinomimeni = [3, 7, 19, 25, 42, 88]
print("Θέση του 42:", dyadiki(taksinomimeni, 42))
```

## Αλγόριθμοι ταξινόμησης

### 1. Φυσαλίδα (Bubble Sort) — O(n²)

```python
def fysalida(lst):
    a = lst[:]
    n = len(a)
    for i in range(n - 1):
        allagi = False
        for j in range(n - 1 - i):
            if a[j] > a[j + 1]:
                a[j], a[j + 1] = a[j + 1], a[j]
                allagi = True
        if not allagi:      # βελτιστοποίηση: ήδη ταξινομημένη
            break
    return a

print(fysalida([42, 7, 19, 3, 25]))
```

### 2. Επιλογή (Selection Sort) — O(n²)

```python
def epilogi(lst):
    a = lst[:]
    for i in range(len(a)):
        min_thesi = i
        for j in range(i + 1, len(a)):
            if a[j] < a[min_thesi]:
                min_thesi = j
        a[i], a[min_thesi] = a[min_thesi], a[i]
    return a

print(epilogi([42, 7, 19, 3, 25]))
```

### 3. Εισαγωγή (Insertion Sort) — O(n²), γρήγορη σε σχεδόν ταξινομημένα

```python
def eisagogi(lst):
    a = lst[:]
    for i in range(1, len(a)):
        kleidi = a[i]
        j = i - 1
        while j >= 0 and a[j] > kleidi:
            a[j + 1] = a[j]
            j -= 1
        a[j + 1] = kleidi
    return a

print(eisagogi([42, 7, 19, 3, 25]))
```

### 4. Συγχώνευση (Merge Sort) — O(n log n)

```python
def sygchoneysi(lst):
    if len(lst) <= 1:
        return lst[:]
    mid = len(lst) // 2
    aristera = sygchoneysi(lst[:mid])
    dexia = sygchoneysi(lst[mid:])

    apotelesma = []
    i = j = 0
    while i < len(aristera) and j < len(dexia):
        if aristera[i] <= dexia[j]:
            apotelesma.append(aristera[i]); i += 1
        else:
            apotelesma.append(dexia[j]); j += 1
    apotelesma.extend(aristera[i:])
    apotelesma.extend(dexia[j:])
    return apotelesma

print(sygchoneysi([42, 7, 19, 3, 25, 88, 1]))
```

## Σύγκριση

| Αλγόριθμος | Χειρότερη | Μέση | Καλύτερη | Σταθερός |
| --- | --- | --- | --- | --- |
| Φυσαλίδα | O(n²) | O(n²) | O(n) | ✅ |
| Επιλογή | O(n²) | O(n²) | O(n²) | ❌ |
| Εισαγωγή | O(n²) | O(n²) | O(n) | ✅ |
| Συγχώνευση | O(n log n) | O(n log n) | O(n log n) | ✅ |

!!! tip "Στη πράξη"
    Η Python χρησιμοποιεί **Timsort** (`sorted()`, `list.sort()`) — υβρίδιο merge/insertion sort με O(n log n).

## Ασκήσεις

1. Μέτρησε τις συγκρίσεις που κάνει κάθε αλγόριθμος για την ίδια λίστα.
2. Υλοποίησε τη δυαδική αναζήτηση αναδρομικά.
3. Πότε η ταξινόμηση εισαγωγής είναι προτιμότερη από τη συγχώνευση;