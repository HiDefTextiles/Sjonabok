"""Image-and-words features from an image-text model (CLIP), no labels used.

CLIP (Radford et al. 2021, https://arxiv.org/abs/2103.00020) was trained on
pictures with their captions, so it can say how well a picture fits a phrase
such as "a cross-stitch embroidery chart of a bird". Here the open
re-trained version OpenCLIP ViT-B/32 (LAION-2B, https://github.com/mlfoundations/open_clip)
scores every chart against the phrases in prompts.csv. The phrases are the
only human input: words for what the reviewer looks for, chosen once, never
the labels of any chart.

Two distances come out:
    work/clip_all_dist.csv          1 minus cosine similarity of the CLIP image
                                    descriptions (like the DINOv2 distance)
    work/all/clip_text_dist.csv     distance between the charts' scores for each
                                    group of phrases (animals, plants, ornament,
                                    letters), each score relative to its average
                                    over all charts, so a group the model favours
                                    everywhere does not swamp the rest
and work/clip_scores.csv keeps the scores per chart.

    HF_HUB_DISABLE_XET=1 python3 clip_features.py --txt ../../patterns/txt

Needs torch and open_clip_torch, and the first time huggingface.co (~600 MB).
"""

import argparse
import csv
import hashlib
import numpy as np
from PIL import Image

from subjects import ALL, BAND_KINDS, HERE, PILOT_KINDS, WORK, Corpus, read_csv, write_matrix

MODEL, PRETRAINED = "ViT-B-32", "laion2b_s34b_b79k"
PROMPTS = HERE / "prompts.csv"


class ClipScorer:
    def __init__(self, model=MODEL, pretrained=PRETRAINED, seed=1):
        import open_clip
        import torch
        torch.manual_seed(seed)
        torch.set_num_threads(4)
        self.torch = torch
        self.model, _, self.pre = open_clip.create_model_and_transforms(model, pretrained=pretrained)
        self.model.eval()
        self.tok = open_clip.get_tokenizer(model)

    def weights_hash(self):
        h = hashlib.sha256()
        for k, v in sorted(self.model.state_dict().items()):
            h.update(k.encode())
            h.update(v.detach().cpu().numpy().tobytes())
        return h.hexdigest()

    @staticmethod
    def render(cells, size=224):
        """Black on white, whole cells kept sharp, centred in a white square."""
        h, w = cells.shape
        zoom = max(1, (size - 16) // max(h, w))
        img = Image.fromarray(np.where(cells == 1, 0, 255).astype(np.uint8))
        img = img.resize((w * zoom, h * zoom), Image.NEAREST)
        img.thumbnail((size - 16, size - 16), Image.NEAREST)
        sq = Image.new("RGB", (size, size), "white")
        sq.paste(img.convert("RGB"), ((size - img.width) // 2, (size - img.height) // 2))
        return sq

    def images(self, charts, batch=32):
        out = []
        with self.torch.no_grad():
            for k in range(0, len(charts), batch):
                x = self.torch.stack([self.pre(self.render(np.asarray(c))) for c in charts[k:k + batch]])
                v = self.model.encode_image(x)
                out.append((v / v.norm(dim=-1, keepdim=True)).numpy())
        return np.concatenate(out)

    def texts(self, phrases):
        with self.torch.no_grad():
            t = self.model.encode_text(self.tok(phrases))
            return (t / t.norm(dim=-1, keepdim=True)).numpy()


def main():
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--txt", default="../../patterns/txt")
    a = ap.parse_args()
    units = Corpus(a.txt, PILOT_KINDS + BAND_KINDS).units
    ids = [u.id for u in units]
    prompts = read_csv(PROMPTS)
    template = next(r["phrase"] for r in prompts if r["group"] == "template")
    prompts = [r for r in prompts if r["group"] != "template"]
    groups = list(dict.fromkeys(r["group"] for r in prompts))

    cs = ClipScorer()
    # bands are shown repeated (3 times along), motifs as drawn
    v = cs.images([u.tiled() if u.kind in BAND_KINDS else u.cells for u in units])
    t = cs.texts([template.format(r["phrase"]) for r in prompts])
    logits = 100 * v @ t.T
    p = np.exp(logits - logits.max(1, keepdims=True))
    p /= p.sum(1, keepdims=True)
    score = np.stack([p[:, [i for i, r in enumerate(prompts) if r["group"] == g]].sum(1) for g in groups], 1)

    d = np.clip(1.0 - v @ v.T, 0.0, 2.0)
    np.fill_diagonal(d, 0.0)
    write_matrix(WORK / "clip_all_dist.csv", ids, d)
    z = np.log(score + 1e-6)
    z = (z - z.mean(0)) / z.std(0)
    d = np.sqrt(((z[:, None, :] - z[None, :, :]) ** 2).sum(-1))
    np.fill_diagonal(d, 0.0)
    ALL.mkdir(parents=True, exist_ok=True)
    write_matrix(ALL / "clip_text_dist.csv", ids, d)
    with open(WORK / "clip_scores.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["id"] + groups)
        for i, row in zip(ids, score):
            w.writerow([i] + [f"{x:.4f}" for x in row])
    (WORK / "clip_model.txt").write_text(f"open_clip:{MODEL}:{PRETRAINED}\nsha256 {cs.weights_hash()}\n")
    print(f"{len(ids)} charts scored against {len(prompts)} phrases with {MODEL} ({PRETRAINED})")


if __name__ == "__main__":
    main()
