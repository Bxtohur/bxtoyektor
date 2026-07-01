"""Search Engine in-memory (PRD F-2.1..F-2.3, §8.2).

Index sederhana yang di-rebuild setiap kali data di-refresh. Mendukung:
- pencarian substring cepat (target < 300 ms untuk ±2.000 baris),
- filter per sheet/kategori (F-2.2),
- fallback fuzzy/typo-tolerant via rapidfuzz (F-2.3).

Murni logika (tanpa Qt) agar mudah diuji.
"""
from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

from ..data.models import DocumentItem


@dataclass(slots=True)
class HasilPencarian:
    item: DocumentItem
    skor: float  # 0..100, makin tinggi makin cocok


class SearchIndex:
    """Index in-memory atas kumpulan DocumentItem."""

    def __init__(self, items: list[DocumentItem] | None = None) -> None:
        self._items: list[DocumentItem] = []
        self._teks: list[str] = []  # teks_cari lowercase, paralel dg _items
        if items:
            self.rebuild(items)

    def rebuild(self, items: list[DocumentItem]) -> None:
        """Bangun ulang index dari daftar item baru."""
        self._items = list(items)
        self._teks = [it.teks_cari.lower() for it in self._items]

    @property
    def sheets(self) -> list[str]:
        """Daftar sheet unik (urut kemunculan)."""
        out: list[str] = []
        for it in self._items:
            if it.sheet not in out:
                out.append(it.sheet)
        return out

    def cari(
        self,
        query: str,
        *,
        sheet: str | None = None,
        fuzzy: bool = True,
        limit: int = 200,
        skor_min_fuzzy: float = 60.0,
    ) -> list[HasilPencarian]:
        """Cari dokumen.

        - `query` kosong → kembalikan semua (terfilter sheet), tanpa skor.
        - Cocokkan substring dulu; bila `fuzzy`, tambahkan hasil fuzzy untuk
          item yang belum cocok substring.
        - `sheet` membatasi hasil ke satu sheet (F-2.2).
        """
        q = query.strip().lower()
        idxs = range(len(self._items))
        if sheet:
            idxs = [i for i in idxs if self._items[i].sheet == sheet]

        if not q:
            return [HasilPencarian(self._items[i], 100.0) for i in idxs][:limit]

        hasil: list[HasilPencarian] = []
        sisa: list[int] = []
        for i in idxs:
            if q in self._teks[i]:
                # skor lebih tinggi bila cocok di awal nama_file
                awal = self._items[i].nama_file.lower().startswith(q)
                hasil.append(HasilPencarian(self._items[i], 100.0 if awal else 90.0))
            else:
                sisa.append(i)

        if fuzzy and len(q) >= 3:
            for i in sisa:
                skor = fuzz.partial_ratio(q, self._teks[i])
                if skor >= skor_min_fuzzy:
                    hasil.append(HasilPencarian(self._items[i], float(skor)))

        hasil.sort(key=lambda h: (-h.skor, h.item.nama_file.lower()))
        return hasil[:limit]
