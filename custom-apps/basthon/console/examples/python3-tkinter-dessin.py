# Un petit logiciel de dessin avec tkinter : une palette de couleurs, une
# épaisseur réglable, et une boîte de dialogue avant de tout effacer.

import tkinter as tk
from tkinter import messagebox

LARGEUR, HAUTEUR = 480, 320
COULEURS = ["#ef476f", "#ffd166", "#06d6a0", "#118ab2", "#073b4c"]

fenetre = tk.Tk()
fenetre.title("Dessin")

couleur = tk.StringVar(fenetre, COULEURS[0])
epaisseur = tk.IntVar(fenetre, 4)

# barre d'outils : couleurs, épaisseur, effacer
outils = tk.Frame(fenetre)
outils.pack(fill="x", padx=6, pady=6)
for c in COULEURS:
    tk.Radiobutton(outils, bg=c, selectcolor=c, activebackground=c,
                   indicatoron=False, width=3, variable=couleur,
                   value=c).pack(side="left", padx=2)
tk.Scale(outils, from_=1, to=20, orient="horizontal", label="Épaisseur",
         variable=epaisseur, length=140).pack(side="left", padx=12)

toile = tk.Canvas(fenetre, width=LARGEUR, height=HAUTEUR, bg="white",
                  cursor="pencil")
toile.pack(padx=6)

precedent = None  # dernier point du tracé en cours


def appui(evenement):
    global precedent
    precedent = (evenement.x, evenement.y)


def glisser(evenement):
    global precedent
    toile.create_line(*precedent, evenement.x, evenement.y,
                      fill=couleur.get(), width=epaisseur.get(),
                      capstyle="round", tags="trait")
    precedent = (evenement.x, evenement.y)


toile.bind("<ButtonPress-1>", appui)
toile.bind("<B1-Motion>", glisser)


def effacer():
    # la boîte de dialogue attend la réponse, comme avec le vrai tkinter
    if messagebox.askyesno("Effacer", "Effacer tout le dessin ?"):
        toile.delete("trait")


tk.Button(outils, text="Effacer…", command=effacer).pack(side="right")

fenetre.mainloop()
