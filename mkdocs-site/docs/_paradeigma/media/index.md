# 🎬 Πολυμέσα

Συλλογή εκπαιδευτικού υλικού σε μορφή βίντεο, ήχου, PDF και διαφανειών.

## 📁 Φάκελοι υλικού

| Φάκελος | Περιεχόμενο | Διαδρομή |
| --- | --- | --- |
| 🎥 **Βίντεο** | Μαγνητοσκοπημένα μαθήματα και επιδείξεις | `videos/` |
| 🔊 **Ήχος** | Ακουστικές επεξηγήσεις, podcasts | `audio/` |
| 📄 **PDF** | Φύλλα εργασίας, σημειώσεις, ασκήσεις | `pdfs/` |
| 🖼️ **Διαφάνειες** | Παρουσιάσεις μαθημάτων | `slides/` |

## Πώς προσθέτουμε υλικό

### Βίντεο

```markdown
<video controls width="100%">
  <source src="../../videos/mathima-01.mp4" type="video/mp4">
  Ο περιηγητής σου δεν υποστηρίζει βίντεο.
</video>
```

### Ήχος

```markdown
<audio controls>
  <source src="../../audio/epexigisi-01.mp3" type="audio/mpeg">
</audio>
```

### PDF (ενσωμάτωση)

```markdown
[📄 Κατέβασε το φύλλο εργασίας](../pdfs/fyllo-ergasias-01.pdf){ .md-button }

<object data="../pdfs/fyllo-ergasias-01.pdf" type="application/pdf" width="100%" height="600px">
  <a href="../pdfs/fyllo-ergasias-01.pdf">Άνοιγμα PDF</a>
</object>
```

### Εικόνες με lightbox

Οι εικόνες ανοίγουν αυτόματα σε μεγέθυνση (mkdocs-glightbox):

```markdown
![Διάγραμμα ροής](../assets/diagramma.png)
```

!!! info "Αυτόματο lightbox"
    Κάθε εικόνα που προστίθεται στο υλικό αποκτά αυτόματα λειτουργία μεγέθυνσης, πλοήγηση με swipe και λεζάντα.

## 📤 Ανέβασμα αρχείων

Οι εκπαιδευτικοί μπορούν να ανεβάζουν αρχεία μέσω του **Visual Pandoc Studio** (`/pandoc/`) ή απευθείας στους φακέλους:

```bash
/opt/school-portal/mkdocs-site/docs/videos/
/opt/school-portal/mkdocs-site/docs/audio/
/opt/school-portal/mkdocs-site/docs/pdfs/
/opt/school-portal/mkdocs-site/docs/slides/
```

Μετά την προσθήκη, το υλικό ενημερώνεται αυτόματα (systemd path unit) ή χειροκίνητα:

```bash
sudo systemctl start school-mkdocs.service
```