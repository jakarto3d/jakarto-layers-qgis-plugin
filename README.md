# Jakarto layers QGIS Plugin

Prototype to view and edit Jakarto layers in QGIS.

## Concept

Les "layers Jakarto" sont des couches de géométries vectorielles stockées sur le serveur de Jakarto.

Le but est de pouvoir les charger et les éditer dans QGIS, et qu'ils soient synchronisés avec les autres services de Jakarto (jakartowns, etc.). QGIS n'est pas requis, on peut s'en servir pour partager des données entre collègues sur Jakartowns seulement.

## Roadmap

- [x] Afficher les layers dans QGIS
- [x] Créer et modifier des points sur les layers, et que ce soit synchronisé avec la base de données supabase
- [x] Écouter les modifications sur les layers dans supabase et les appliquer aux layers dans QGIS.
- [ ] Afficher les layers dans Jakartowns
- [ ] Créer et modifier des points sur les layers dans Jakartowns et que ce soit synchronisé avec la base de données supabase
- [x] ~~Imbriquer un navigateur Chrome dans QGIS pour afficher Jakartowns~~ (voir note [1])
- [ ] Implémenter pour les autres types de géométries
- [ ] Implémenter la protection et les droits d'accès des couches
- [ ] Pour aider à la localisation, afficher un point à l'endroit où l'utilisateur se trouve dans le navigateur Jakartowns (comme le curseur jaune sur la minimap de Jakartowns)

## Installation

Le projet est encore très prototype, il se peut qu'il manque des étapes dans cette liste (notamment, le développement sous Windows n'est pas encore considéré):

- Suivre les instructions pour [installer supabase en self host](https://supabase.com/docs/guides/self-hosting/docker)
- Ouvrir QGIS avec le repo comme dossier de plugin: `just run-qgis`
- Installer "Jakarto layers qgis plugin" dans le menu des plugins QGIS.
- Débugger parce que ça ne s'est probablement pas passé comme sur des roulettes.

Voir `just` pour d'autres commandes de développement.

## Notes

[1] Abandonné, QtWebKit n'est pas utilisable (un vieux safari de 2016), et l'installation de QtWebEngine n'est pas assez fluide pour le recommander aux utilisateurs. Une fois en place, on pourrait toujours supporter les 2, donc on pourrait afficher le panel avec Jakartowns quand QtWebEngine fonctionne, mais utiliser un navigateur web standard séparé quand il n'est pas disponible.
