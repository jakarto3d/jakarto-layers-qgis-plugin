# Jakarto layers QGIS Plugin

Prototype to view and edit Jakarto layers in QGIS.


## Concept

Les "layers Jakarto" sont des couches de géométries vectorielles stockées sur le serveur de Jakarto.

Le but est de pouvoir les charger et les éditer dans QGIS, et qu'ils soient synchronisés avec les autres services de Jakarto (jakartowns, etc.). QGIS n'est pas requis, on peut s'en servir pour partager des données entre collègues sur Jakartowns seulement.

## Architecture

```mermaid
architecture-beta
    group plugin[Plugin]
    group adapter[Adapter] in plugin

    service qgis(database)[QGIS]
    service supabase(cloud)[Supabase]
    service postgrest(internet)[Postgrest] in plugin
    service realtime(internet)[Supabase Realtime Events] in plugin
    service converters(database)[Converters] in adapter
    service layers(database)[Layers] in adapter

    qgis:R <--> L:converters{group}
    converters{group}:R -- L:postgrest
    converters{group}:R -- L:realtime
    layers:T -- B:converters
    postgrest:R <--> L:supabase
    realtime:R <-- B:supabase
```

`Adapter` s'occupe d'écouter les évènements, transformer les features (`Converters`) et les passer soit à QGIS, soit à Supabase. Pour se connecter à QGIS, il utilise les fonctionnalités de plugin QGIS. Pour se connecter à Supabase, il utilise les librairies `postgrest` (pour les évènements de QGIS) et `realtime` (pour les évènements externes).

Les features sont stockées en mémoire dans l'adapter dans un objet qui contient l'id QGIS et supabase pour pouvoir les associer.

Il y a 6 types d'évènements:

- `qgis_insert_event`: une feature est créée dans QGIS
- `qgis_update_event`: une feature est mise à jour dans QGIS
- `qgis_delete_event`: une feature est supprimée dans QGIS
- `supabase_insert_event`: une feature est créée dans Supabase
- `supabase_update_event`: une feature est mise à jour dans Supabase
- `supabase_delete_event`: une feature est supprimée dans Supabase

Chaque évènement est traduit en une requête:

- `qgis_insert_event` -> `supabase_insert_request`
- `qgis_update_event` -> `supabase_update_request`
- `qgis_delete_event` -> `supabase_delete_request`
- `supabase_insert_event` -> `qgis_insert_request`
- `supabase_update_event` -> `qgis_update_request`
- `supabase_delete_event` -> `qgis_delete_request`

Pour chaque évènement, l'adapter va le transformer et le passer à l'autre service (soit QGIS, soit Supabase). Il doit aussi ignorer le prochain message, par exemple:

- `qgis_insert_event` -> `supabase_insert_request` -> La feature est envoyée à Supabase
- `supabase_insert_event` -> On reçoit un message, mais pour la même feature qui vient d'être créée, on ignore le message

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
- Le plugin "Plugin Reloader" est recommandé pour le développement, il fonctionne bien avec ce projet.
- Débugger parce que ça ne s'est probablement pas passé comme sur des roulettes.

Voir `just` pour d'autres commandes de développement.

## Notes

[1] Abandonné, QtWebKit n'est pas utilisable (un vieux safari de 2016), et l'installation de QtWebEngine n'est pas assez fluide pour le recommander aux utilisateurs. Une fois en place, on pourrait toujours supporter les 2, donc on pourrait afficher le panel avec Jakartowns quand QtWebEngine fonctionne, mais utiliser un navigateur web standard séparé quand il n'est pas disponible.
