# TrendSwap · test vidéo

**Live : https://hatimhtm.github.io/deepfake-test/**

Une page, un test : dépose la photo d'une persona et le reel d'un modèle, la
persona rejoue le reel (mouvement, gestes, expressions, lèvres). Le son
d'origine est remis dessous.

## Ce que c'est

- Une seule expérience, sur l'API hébergée **Kling 2.6 motion control** (kie.ai).
- 100 % statique : la clé API est collée dans la page et ne quitte pas le
  navigateur (elle ne va qu'à kie.ai). Rien n'est stocké ici.
- Coût mesuré sur le premier clip : 9,7 s → 99 crédits ≈ 0,50 $, 410 s.

## Ce que ce n'est pas

- Pas notre modèle, pas notre GPU, pas notre décor : dans ce mode le décor vient
  de la photo de la persona, pas du reel. Pour garder le décor du reel il faut
  d'abord placer la persona dans une image du reel.
- Pas le volume : chaque clip passe par un filtre tiers et une file d'attente.

## La suite

La version production est **SCAIL-2** (Wan 2.1, remplacement de personnage,
Apache 2.0, intégré à ComfyUI 0.34) sur notre propre endpoint RunPod : décor du
reel conservé, pas de filtre tiers, quelques centimes par clip. Le worker
(`worker/handler.py`) et le workflow officiel sont prêts ; il manque le budget
RunPod pour l'endpoint dédié (GPU 80 Go) et le stockage des poids (~40 Go).
