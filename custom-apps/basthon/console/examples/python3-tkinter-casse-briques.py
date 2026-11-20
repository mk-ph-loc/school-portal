# Un casse-briques avec tkinter : la raquette suit la souris (ou les flèches
# du clavier), trois vies, des niveaux de plus en plus rapides. Un clic dans
# le jeu lance la partie.

import tkinter as tk

LARGEUR, HAUTEUR = 520, 400
COULEURS = ["#ef476f", "#f78c6b", "#ffd166", "#06d6a0", "#118ab2"]

fenetre = tk.Tk()
fenetre.title("Casse-briques")
fenetre.resizable(False, False)
jeu = tk.Canvas(fenetre, width=LARGEUR, height=HAUTEUR, bg="#073b4c",
                highlightthickness=0)
jeu.pack()

etat = {"niveau": 1, "score": 0, "vies": 3, "en_cours": False, "pause": False}


def placer_briques():
    for ligne, c in enumerate(COULEURS):
        for colonne in range(10):
            x, y = 10 + colonne * 50, 40 + ligne * 22
            jeu.create_rectangle(x, y, x + 46, y + 18, fill=c, outline="",
                                 tags="brique")


def nouvelle_balle():
    jeu.coords(etat["balle"], LARGEUR / 2 - 7, HAUTEUR - 60,
               LARGEUR / 2 + 7, HAUTEUR - 46)
    vitesse = 3 + etat["niveau"]
    etat["dx"], etat["dy"] = vitesse, -vitesse


def nouvelle_partie(niveau=1, attendre=False):
    jeu.delete("all")
    if niveau == 1:
        etat["score"], etat["vies"] = 0, 3
    etat["niveau"], etat["pause"] = niveau, False
    placer_briques()
    etat["raquette"] = jeu.create_rectangle(
        LARGEUR / 2 - 40, HAUTEUR - 30, LARGEUR / 2 + 40, HAUTEUR - 20,
        fill="#e0fbfc", outline="")
    etat["balle"] = jeu.create_oval(0, 0, 0, 0, fill="white", outline="")
    etat["texte"] = jeu.create_text(10, 14, anchor="w", fill="#e0fbfc",
                                    font=("Arial", 12, "bold"))
    nouvelle_balle()
    afficher_score()
    if attendre:
        message("Cliquer pour jouer")
    elif not etat["en_cours"]:
        etat["en_cours"] = True
        boucle()


def afficher_score():
    jeu.itemconfigure(etat["texte"], text=f"Niveau {etat['niveau']}    "
                      f"Score {etat['score']}    Vies {etat['vies']}")


def message(texte, couleur="white"):
    jeu.create_text(LARGEUR / 2, HAUTEUR / 2 + 40, text=texte, fill=couleur,
                    font=("Arial", 18, "bold"), justify="center")


def placer_raquette(x):
    x1, _, x2, _ = jeu.coords(etat["raquette"])
    demi = (x2 - x1) / 2
    x = max(demi, min(LARGEUR - demi, x))
    jeu.move(etat["raquette"], x - (x1 + demi), 0)


def boucle():
    balle = etat["balle"]
    jeu.move(balle, etat["dx"], etat["dy"])
    x1, y1, x2, y2 = jeu.coords(balle)
    # rebonds sur les bords
    if x1 <= 0:
        etat["dx"] = abs(etat["dx"])
    if x2 >= LARGEUR:
        etat["dx"] = -abs(etat["dx"])
    if y1 <= 30:
        etat["dy"] = abs(etat["dy"])
    # balle perdue
    if y2 >= HAUTEUR:
        etat["vies"] -= 1
        afficher_score()
        if etat["vies"] == 0:
            etat["en_cours"] = False
            message("Perdu !\nCliquer pour rejouer")
            return
        nouvelle_balle()
    # chocs avec la raquette ou une brique
    for objet in jeu.find_overlapping(x1, y1, x2, y2):
        if objet == etat["raquette"]:
            # l'angle dépend de l'endroit où la balle touche la raquette
            r1, _, r2, _ = jeu.coords(objet)
            decalage = ((x1 + x2) / 2 - (r1 + r2) / 2) / ((r2 - r1) / 2)
            etat["dx"] = max(-8, min(8, etat["dx"] + 3 * decalage))
            etat["dy"] = -abs(etat["dy"])
        elif "brique" in jeu.gettags(objet):
            jeu.delete(objet)
            etat["dy"] = -etat["dy"]
            etat["score"] += 10 * etat["niveau"]
            afficher_score()
            if not jeu.find_withtag("brique"):
                # niveau suivant, un peu plus rapide
                message(f"Niveau {etat['niveau'] + 1} !", "#ffd166")
                fenetre.after(1500, nouvelle_partie, etat["niveau"] + 1)
                etat["en_cours"], etat["pause"] = False, True
                return
            break
    fenetre.after(16, boucle)


def clic(evenement):
    jeu.focus_set()  # pour les flèches du clavier
    if not etat["en_cours"] and not etat["pause"]:
        nouvelle_partie()


jeu.bind("<Motion>", lambda e: placer_raquette(e.x))
jeu.bind("<Button-1>", clic)
jeu.bind("<Left>", lambda e: placer_raquette(jeu.coords(etat["raquette"])[0] + 10))
jeu.bind("<Right>", lambda e: placer_raquette(jeu.coords(etat["raquette"])[0] + 70))

nouvelle_partie(attendre=True)
fenetre.mainloop()
