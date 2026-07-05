'use strict';

const audio = document.getElementById('bg-audio');
const toggle = document.getElementById('audio-toggle');
const icon = toggle.querySelector('i');

toggle.addEventListener('click', () => {
  if (audio.paused) audio.play();
  else audio.pause();
});

audio.addEventListener('play', () => {
  toggle.classList.add('playing');
  toggle.setAttribute('aria-pressed', 'true');
  toggle.setAttribute('aria-label', 'Pause Winterfylleth (reprise)');
  icon.className = 'fa-solid fa-pause';
});

audio.addEventListener('pause', () => {
  toggle.classList.remove('playing');
  toggle.setAttribute('aria-pressed', 'false');
  toggle.setAttribute('aria-label', 'Play Winterfylleth (reprise)');
  icon.className = 'fa-solid fa-play';
});
