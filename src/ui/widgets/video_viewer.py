"""Pemutar video (PRD F-3.x diperluas: dukungan video presentasi).

Membungkus QMediaPlayer + QVideoWidget. Dipakai di panel operator (dengan
kontrol play/pause & seek) dan di jendela proyektor (kontrol bisa disembunyikan
untuk tampilan bersih).
"""
from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QUrl
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import QHBoxLayout, QPushButton, QSlider, QVBoxLayout, QWidget


def _format_waktu(ms: int) -> str:
    d = ms // 1000
    return f"{d // 60:02d}:{d % 60:02d}"


class VideoViewer(QWidget):
    def __init__(self, kontrol: bool = True, parent=None) -> None:
        super().__init__(parent)
        self.setStyleSheet("background:#000;")
        self._player = QMediaPlayer(self)
        self._audio = QAudioOutput(self)
        self._audio.setVolume(1.0)  # pastikan volume penuh (default device)
        self._player.setAudioOutput(self._audio)
        self._video = QVideoWidget(self)
        self._player.setVideoOutput(self._video)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._video, 1)

        self._punya_kontrol = kontrol
        if kontrol:
            layout.addLayout(self._bangun_kontrol())
            self._player.positionChanged.connect(self._on_posisi)
            self._player.durationChanged.connect(self._on_durasi)
            self._player.playbackStateChanged.connect(self._sinkron_tombol)

    def _bangun_kontrol(self) -> QHBoxLayout:
        bar = QHBoxLayout()
        self.btn_play = QPushButton("⏸ Jeda")
        self.btn_play.clicked.connect(self.toggle_play)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, 0)
        self.slider.sliderMoved.connect(self._player.setPosition)
        self.btn_stop = QPushButton("⏹")
        self.btn_stop.clicked.connect(self.stop)
        for w in (self.btn_play, self.btn_stop, self.slider):
            bar.addWidget(w)
        return bar

    # ---- API publik ----------------------------------------------------
    @property
    def player(self) -> QMediaPlayer:
        return self._player

    def set_muted(self, muted: bool) -> None:
        self._audio.setMuted(muted)

    def putar(self, path: str | Path, auto_play: bool = True) -> None:
        self._audio.setMuted(False)  # preview: bersuara secara default
        self._player.setSource(QUrl.fromLocalFile(str(Path(path))))
        if auto_play:
            self._player.play()

    def play(self) -> None:
        self._player.play()

    def pause(self) -> None:
        self._player.pause()

    def stop(self) -> None:
        self._player.stop()

    def toggle_play(self) -> None:
        if self._player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self._player.pause()
        else:
            self._player.play()

    def posisi(self) -> int:
        return self._player.position()

    def set_posisi(self, ms: int) -> None:
        self._player.setPosition(ms)

    # ---- internal ------------------------------------------------------
    def _on_posisi(self, ms: int) -> None:
        if not self.slider.isSliderDown():
            self.slider.setValue(ms)

    def _on_durasi(self, ms: int) -> None:
        self.slider.setRange(0, ms)

    def _sinkron_tombol(self, state) -> None:
        playing = state == QMediaPlayer.PlaybackState.PlayingState
        self.btn_play.setText("⏸ Jeda" if playing else "▶ Putar")
