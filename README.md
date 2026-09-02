# TrendSwap · test vidéo

**Live : https://hatimhtm.github.io/deepfake-test/**

Une persona, un reel : la persona rejoue le reel — mouvement, gestes,
expressions, lèvres. Le son d'origine reste dessous.

Deux routes existent, et elles ne servent pas à la même chose.

## 1. Kling 2.6 chez kie.ai — le formulaire de la page

Rien à installer. La clé API est collée dans la page et ne quitte pas le
navigateur.

Mesuré : 9,7 s → 99 crédits ≈ **0,50 $**, 410 s.

Sa limite est structurelle, pas un réglage : **le décor vient de la photo de la
persona, pas du reel.** Un portrait sur fond de salon a mis le modèle dans un
salon et fait disparaître le cornet de glace qu'elle tenait. On peut le
contourner en compositant d'abord la persona dans une image du reel, mais cela
fait deux générations et une image choisie à la main par clip. Et chaque clip
passe par le filtre d'un tiers.

## 2. Wan 2.2 Animate sur notre GPU — construit et mesuré

ComfyUI sur un endpoint RunPod à nous, un H100 loué à la seconde. Le mode
remplacement ne refait pas la scène : il **remplace la personne et garde le
décor du reel**. Le McCafé, les gobelets, la table et les gens au fond sont ceux
du reel, sans montage préalable.

Mesuré sur le même reel, 9,8 s en 480×832 : **131 s de GPU, ≈ 0,15 $** — environ
trois fois moins cher que la route hébergée, et sans filtre tiers.

Défaut connu : ce que la personne tient est à l'intérieur du masque du
personnage, donc régénéré — sur dix secondes le cornet dérive vers un gobelet
rouge et revient. Le décor, lui, ne bouge jamais.

### Ce qui compose cette route

| | |
|---|---|
| `worker/` | L'image du worker : ComfyUI 0.34 + les quatre packs de nœuds du graphe officiel, épinglés au commit. Construite par GitHub Actions vers `ghcr.io/hatimhtm/trendswap-worker`. |
| `worker/handler.py` | Entrées par URL, sorties vers des URL signées fournies par l'appelant — le worker ne détient aucune clé. |
| `scripts/fetch-models.sh` | Remplit le volume réseau (~29 Go) depuis un pod CPU jetable. |
| `pipeline/` | La conversion du graphe éditeur vers le format API, et les pièges qui coûtent une exécution chacun. |
