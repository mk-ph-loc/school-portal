# Un tableau de données (data frame), quelques statistiques et des graphiques.

classe <- data.frame(
  nom = c("Ada", "Alan", "Grace", "Linus", "Margaret", "Dennis"),
  maths = c(17.5, 15.25, 18, 12.75, 16, 11.5),
  info = c(19, 16.5, 17.5, 14, 18.5, 13)
)

classe$moyenne <- (classe$maths + classe$info) / 2

# Trié par moyenne décroissante
classe[order(classe$moyenne, decreasing = TRUE), ]

summary(classe$moyenne)
cor(classe$maths, classe$info)

# Les graphiques s'affichent à côté de la console.
barplot(classe$moyenne, names.arg = classe$nom, col = "steelblue",
        main = "Moyennes de la classe", ylim = c(0, 20))
plot(classe$maths, classe$info, pch = 19, col = "tomato",
     xlab = "Maths", ylab = "Info", main = "Maths et info")
abline(lm(info ~ maths, data = classe), lty = 2)
