# Retouche d'image avec Pillow et tkinter : des curseurs de luminosité, de
# contraste et de saturation, des filtres, et un bouton pour tout annuler.
# Pour retoucher une photo, ouvrez-la dans Basthon puis remplacez l'image
# fabriquée par Image.open("photo.jpg").convert("RGB").

import tkinter as tk
from PIL import Image, ImageDraw, ImageEnhance, ImageFilter, ImageOps, ImageTk

LARGEUR, HAUTEUR = 400, 260


def paysage():
    """Un paysage dessiné avec Pillow : ciel, soleil, montagnes et lac."""
    image = Image.new("RGB", (LARGEUR, HAUTEUR))
    dessin = ImageDraw.Draw(image)
    for y in range(HAUTEUR):
        dessin.line([(0, y), (LARGEUR, y)],
                    fill=(70 + y // 2, 130 + y // 4, 230 - y // 4))
    dessin.ellipse([280, 30, 340, 90], fill="#ffd166")
    dessin.polygon([(0, 190), (90, 80), (170, 170), (250, 60), (400, 190)],
                   fill="#3d5a80")
    dessin.polygon([(70, 104), (90, 80), (110, 104)], fill="white")
    dessin.polygon([(225, 92), (250, 60), (275, 92)], fill="white")
    dessin.rectangle([0, 190, LARGEUR, HAUTEUR], fill="#118ab2")
    for x in range(20, LARGEUR, 60):
        dessin.line([(x, 215), (x + 30, 215)], fill="#8ecae6", width=2)
    return image


originale = paysage()
base = originale  # l'image après les filtres, avant les curseurs

fenetre = tk.Tk()
fenetre.title("Retouche d'image")
photo = ImageTk.PhotoImage(originale)
tk.Label(fenetre, image=photo).pack(padx=6, pady=6)

# les curseurs : 1 laisse l'image inchangée
reglages = {}
curseurs = tk.Frame(fenetre)
curseurs.pack()
for nom in ["Luminosité", "Contraste", "Saturation"]:
    reglages[nom] = tk.DoubleVar(fenetre, 1)
    tk.Scale(curseurs, label=nom, from_=0, to=2, resolution=0.05,
             orient="horizontal", length=130, variable=reglages[nom],
             command=lambda valeur: afficher()).pack(side="left", padx=4)


def afficher():
    """Applique les curseurs à l'image filtrée, puis l'affiche."""
    image = ImageEnhance.Brightness(base).enhance(reglages["Luminosité"].get())
    image = ImageEnhance.Contrast(image).enhance(reglages["Contraste"].get())
    image = ImageEnhance.Color(image).enhance(reglages["Saturation"].get())
    photo.paste(image)  # même taille : l'image affichée est remplacée


def filtrer(filtre):
    global base
    base = filtre(base)
    afficher()


def annuler():
    global base
    base = originale
    for variable in reglages.values():
        variable.set(1)
    afficher()


boutons = tk.Frame(fenetre)
boutons.pack(pady=6)
for texte, filtre in [
    ("Flou", lambda im: im.filter(ImageFilter.GaussianBlur(2))),
    ("Netteté", lambda im: im.filter(ImageFilter.SHARPEN)),
    ("Contours", lambda im: im.filter(ImageFilter.FIND_EDGES)),
    ("Relief", lambda im: im.filter(ImageFilter.EMBOSS)),
    ("Sépia", lambda im: ImageOps.colorize(ImageOps.grayscale(im),
                                           "#2b1d0e", "#f5deb3")),
    ("Postériser", lambda im: ImageOps.posterize(im, 2)),
    ("Miroir", ImageOps.mirror),
]:
    tk.Button(boutons, text=texte,
              command=lambda f=filtre: filtrer(f)).pack(side="left")
tk.Button(boutons, text="Annuler tout", command=annuler).pack(side="left",
                                                               padx=(10, 0))

fenetre.mainloop()
