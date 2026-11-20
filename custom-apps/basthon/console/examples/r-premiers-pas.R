# Le résultat de chaque expression est affiché automatiquement,
# et tout ce qui est défini reste utilisable dans la console.

carre <- function(x) x^2

# R calcule sur des vecteurs entiers d'un coup.
x <- 1:10
carre(x)

for (i in 1:3) cat(i, "au carré vaut", carre(i), "\n")

n <- as.numeric(readline("Un nombre ? "))
cat("Son carré :", carre(n), "\n")

# Une dernière expression : elle est affichée.
summary(carre(x))
