"""Image-model distance between Sjónabók units (optional step).

Each unit is drawn black on white, scaled up with whole cells kept sharp,
and placed in a 224 x 224 square. A pretrained image model, DINOv2 ViT-S/14
(Oquab et al. 2023, https://arxiv.org/abs/2304.07193), turns each picture
into 384 numbers. The numbers are averaged over the unit's 8 flipped and
turned positions, so orientation does not count, and the distance is
1 minus the cosine similarity.

    python3 embed.py --txt ../../patterns/txt

Needs PyTorch and timm (pip install torch timm) and, the first time, network
access to huggingface.co, where timm fetches the published DINOv2 weights
(about 85 MB, then cached).
The run is on CPU in deterministic mode, so it gives the same numbers
every time on the same machine. The model name and the SHA-256 of its
weights are written to work/embed_model.txt.
"""

import argparse
import hashlib
import numpy as np
from PIL import Image

from subjects import BAND_KINDS, PILOT_KINDS, WORK, Corpus, write_matrix

MODEL_NAME = "vit_small_patch14_dinov2.lvd142m"   # DINOv2 ViT-S/14 as published by Meta, via timm
SIZE = 224
MEAN = np.array([0.485, 0.456, 0.406])   # ImageNet normalisation used by DINOv2
STD = np.array([0.229, 0.224, 0.225])


class Embedder:
    """Wraps the model so the rest of the code sees numpy arrays only."""

    def __init__(self, name=MODEL_NAME, seed=1):
        import timm   # imported here so the other steps run without them
        import torch
        torch.manual_seed(seed)
        torch.use_deterministic_algorithms(True)
        torch.set_num_threads(1)
        self.torch = torch
        self.name = name
        # img_size=224 resamples the position table of the 518 px original;
        # num_classes=0 returns the 384-number image description (class token).
        self.model = timm.create_model(name, pretrained=True, img_size=SIZE, num_classes=0).eval()

    def weights_hash(self):
        """SHA-256 of the weights as loaded, so a run can be checked later."""
        h = hashlib.sha256()
        for k, v in sorted(self.model.state_dict().items()):
            h.update(k.encode())
            h.update(v.detach().cpu().numpy().tobytes())
        return h.hexdigest()

    @staticmethod
    def render(cells):
        """Unit -> 224 x 224 RGB array in 0..1, the figure centred."""
        h, w = cells.shape
        zoom = max(1, (SIZE - 16) // max(h, w))
        img = Image.fromarray(np.where(cells == 1, 0, 255).astype(np.uint8))
        img = img.resize((w * zoom, h * zoom), Image.NEAREST)
        img.thumbnail((SIZE - 16, SIZE - 16), Image.NEAREST)
        square = Image.new("L", (SIZE, SIZE), 255)
        square.paste(img, ((SIZE - img.width) // 2, (SIZE - img.height) // 2))
        return np.repeat(np.asarray(square, dtype=float)[:, :, None] / 255.0, 3, axis=2)

    def embed(self, cells):
        pics = [np.rot90(b, k) for b in (cells, cells[:, ::-1]) for k in range(4)]
        x = np.stack([(self.render(p) - MEAN) / STD for p in pics]).transpose(0, 3, 1, 2)
        with self.torch.no_grad():
            v = self.model(self.torch.tensor(x, dtype=self.torch.float32)).numpy()
        v /= np.linalg.norm(v, axis=1, keepdims=True)
        mean = v.mean(axis=0)
        return mean / np.linalg.norm(mean)


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--txt", default="../../patterns/txt")
    ap.add_argument("--all", action="store_true",
                    help="every chart, bands by their repeat unit -> work/embed_all_dist.csv (for features)")
    ap.add_argument("--tile", action="store_true",
                    help="with --all: embed each chart repeated (2 x 2, or 3 repeats of a band) -> work/embed_tiled_dist.csv")
    a = ap.parse_args()
    units = Corpus(a.txt, PILOT_KINDS + BAND_KINDS).units
    if not a.all:
        keep = set(Corpus.read_ids(WORK / "units.csv"))
        units = [u for u in units if u.id in keep]
    e = Embedder()
    v = np.stack([e.embed(u.tiled() if a.tile else u.cells) for u in units])
    d = np.clip(1.0 - v @ v.T, 0.0, 2.0)
    np.fill_diagonal(d, 0.0)
    name = "embed_tiled_dist.csv" if a.tile else "embed_all_dist.csv" if a.all else "embed_dist.csv"
    write_matrix(WORK / name, [u.id for u in units], d)
    (WORK / "embed_model.txt").write_text(f"timm:{MODEL_NAME}\nsha256 {e.weights_hash()}\n")
    print(f"{len(units)} embeddings with {MODEL_NAME}")


if __name__ == "__main__":
    main()
