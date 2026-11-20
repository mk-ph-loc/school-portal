from p5 import *

capture = None

def setup():
    global capture
    createCanvas(320, 240)
    capture = createCapture(VIDEO)
    # la vidéo est dessinée dans le canevas, pas affichée en dessous
    capture.hide()

def draw():
    background(255)
    # la taille de la vidéo n'est connue qu'une fois la caméra ouverte
    if capture.width > 0:
        image(capture, 0, 0, width, width * capture.height / capture.width)

run()
