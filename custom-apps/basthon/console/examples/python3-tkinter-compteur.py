# Une première fenêtre tkinter : un compteur et trois boutons.

import tkinter as tk

fenetre = tk.Tk()
fenetre.title("Compteur")

valeur = tk.IntVar(fenetre, 0)


def ajouter(n):
    valeur.set(valeur.get() + n)


tk.Label(fenetre, textvariable=valeur, font=("Arial", 32), width=6).pack(pady=10)

boutons = tk.Frame(fenetre)
boutons.pack(padx=20, pady=10)
tk.Button(boutons, text="− 1", width=6, command=lambda: ajouter(-1)).pack(side="left")
tk.Button(boutons, text="Zéro", width=6, command=lambda: valeur.set(0)).pack(side="left", padx=10)
tk.Button(boutons, text="+ 1", width=6, command=lambda: ajouter(1)).pack(side="left")

# dans Basthon, mainloop() rend la main tout de suite : la fenêtre reste
# vivante et réagit aux clics
fenetre.mainloop()
