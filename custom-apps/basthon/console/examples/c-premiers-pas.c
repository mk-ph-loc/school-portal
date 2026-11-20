// Pas besoin de main : les instructions s'exécutent directement,
// et tout ce qui est déclaré reste utilisable dans la console.
#include <stdio.h>

int carre(int x) {
    return x * x;
}

for (int i = 1; i <= 10; i++)
    printf("%d² = %d\n", i, carre(i));

int n;
printf("Un entier ? ");
scanf("%d", &n);
printf("Son carré : %d\n", carre(n));

// La dernière expression, sans point-virgule, est affichée avec son type.
carre(n) / 2.0
