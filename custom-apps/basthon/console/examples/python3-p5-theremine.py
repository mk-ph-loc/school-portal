from p5 import *

# Un thérémine : maintenir le clic sur le dessin pour jouer,
# la souris règle la hauteur (horizontalement) et le volume (verticalement).

osc = None
fft = None

def setup():
    global osc, fft
    createCanvas(500, 300)
    osc = Oscillator("triangle")
    osc.amp(0)
    osc.start()
    fft = FFT()

def draw():
    background(30)
    if mouseIsPressed:
        osc.freq(map(mouseX, 0, width, 100, 1000), 0.05)
        osc.amp(map(mouseY, 0, height, 0.5, 0, True), 0.05)
    else:
        osc.amp(0, 0.2)

    # le spectre (jusqu'à 5 kHz environ)
    spectre = list(fft.analyze())[:200]
    noStroke()
    fill(255, 200, 0)
    w = width / len(spectre)
    for i, valeur in enumerate(spectre):
        h = map(valeur, 0, 255, 0, height)
        rect(i * w, height - h, w, h)

    # la forme de l'onde
    onde = list(fft.waveform())
    noFill()
    stroke(0, 200, 255)
    strokeWeight(2)
    beginShape()
    for i in range(0, len(onde), 4):
        vertex(map(i, 0, len(onde), 0, width), map(onde[i], -1, 1, height, 0))
    endShape()

    noStroke()
    fill(255)
    text("Maintenir le clic pour jouer", 10, 20)

run()
