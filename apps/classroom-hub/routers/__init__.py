"""
Classroom Hub — APIRouters ανά domain (Task 3 architecture review).

  commands.py    ανακοινώσεις/βραβεία, τυχαία επιλογή, πλοήγηση (+ διαχείριση)
  polls.py       cmd_poll + CRUD + bulk + ws vote
  quizzes.py     cmd_quiz + CRUD + αποτελέσματα + ws submit
  timers.py      timers + anchors ωραρίου + γεγονότα τέλους ημέρας/ώρας
  chat_forum.py  chat ιστορικό/mutes/forum (REST + WS handlers)
  config_xlsx.py ενιαίο πρότυπο Excel (12 καρτέλες) + upload → config.json
  catalog.py     κατάλογος μαθημάτων & σύνδεσμοι σύνθετης ανακοίνωσης

Κανένα router δεν κάνει import άλλο router ή το presence — το κοινό state
ζει στο state.py και οι WS handlers καλούνται από το presence.hub_socket.
"""