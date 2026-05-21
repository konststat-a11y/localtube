document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) {
    return;
  }

  const submitter = event.submitter;
  if (submitter instanceof HTMLButtonElement) {
    submitter.disabled = true;
    submitter.dataset.originalText = submitter.textContent || "";
    submitter.textContent = "Подождите...";
  }
});

function formatTime(value) {
  if (!Number.isFinite(value)) {
    return "0:00";
  }

  const totalSeconds = Math.max(0, Math.floor(value));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  const paddedSeconds = String(seconds).padStart(2, "0");
  if (hours > 0) {
    return `${hours}:${String(minutes).padStart(2, "0")}:${paddedSeconds}`;
  }
  return `${minutes}:${paddedSeconds}`;
}

function clamp(value, min, max) {
  return Math.min(max, Math.max(min, value));
}

function initWatchPlayer() {
  const watchPage = document.querySelector("[data-watch-page]");
  if (!watchPage) {
    return;
  }

  const playerArea = watchPage.querySelector("[data-player-area]");
  const video = watchPage.querySelector("[data-player]");
  const playToggle = watchPage.querySelector("[data-play-toggle]");
  const theaterToggle = watchPage.querySelector("[data-theater-toggle]");
  const fullscreenToggle = watchPage.querySelector("[data-fullscreen-toggle]");
  const recommendationsToggle = watchPage.querySelector("[data-recommendations-toggle]");
  const speedSelect = watchPage.querySelector("[data-speed]");
  const timeline = watchPage.querySelector("[data-timeline]");
  const volumeInput = watchPage.querySelector("[data-volume]");
  const autoplayInput = watchPage.querySelector("[data-autoplay]");
  const autoplayCountdown = watchPage.querySelector("[data-autoplay-countdown]");
  const autoplayCountdownValue = watchPage.querySelector("[data-autoplay-countdown-value]");
  const currentTimeEl = watchPage.querySelector("[data-current-time]");
  const durationEl = watchPage.querySelector("[data-duration]");
  const nextUrl = watchPage.dataset.nextUrl || "";
  let lastHorizontalKey = "";
  let lastHorizontalAt = 0;
  let horizontalPressCount = 0;
  let lastAudibleVolume = 1;
  let autoplayCountdownTimer = null;
  let autoplayCountdownSeconds = 5;

  if (!(video instanceof HTMLVideoElement) || !playerArea) {
    return;
  }

  const savedTheater = localStorage.getItem("localtube:theater") === "1";
  const savedCollapsed = localStorage.getItem("localtube:recommendationsCollapsed") === "1";
  const savedAutoplay = localStorage.getItem("localtube:autoplay") === "1";
  const savedVolume = Number(localStorage.getItem("localtube:volume"));
  const savedSpeed = Number(localStorage.getItem("localtube:speed"));

  if (savedTheater) {
    watchPage.classList.add("theater-mode");
    theaterToggle?.classList.add("is-active");
    theaterToggle?.setAttribute("aria-pressed", "true");
  }
  if (savedCollapsed) {
    watchPage.classList.add("recommendations-collapsed");
    recommendationsToggle?.setAttribute("aria-pressed", "true");
  }
  if (autoplayInput instanceof HTMLInputElement) {
    autoplayInput.checked = savedAutoplay;
  }
  if (Number.isFinite(savedVolume)) {
    video.volume = clamp(savedVolume, 0, 1);
  }
  if (video.volume > 0) {
    lastAudibleVolume = video.volume;
  }
  if (volumeInput instanceof HTMLInputElement) {
    volumeInput.value = String(video.volume);
  }
  if (Number.isFinite(savedSpeed) && savedSpeed > 0) {
    video.playbackRate = savedSpeed;
    if (speedSelect instanceof HTMLSelectElement) {
      speedSelect.value = String(savedSpeed);
    }
  }

  function updatePlayState() {
    if (playToggle) {
      playToggle.textContent = video.paused ? "▶" : "Ⅱ";
      playToggle.setAttribute("aria-label", video.paused ? "Воспроизвести" : "Пауза");
    }
    playerArea.classList.toggle("is-paused", video.paused);
  }

  function updateVolumeState() {
    if (!video.muted && video.volume > 0) {
      lastAudibleVolume = video.volume;
    }
    if (volumeInput instanceof HTMLInputElement) {
      volumeInput.value = String(video.muted ? 0 : video.volume);
    }
    localStorage.setItem("localtube:volume", String(video.volume));
  }

  function updateTimeline() {
    const duration = video.duration || 0;
    const current = video.currentTime || 0;
    if (timeline instanceof HTMLInputElement) {
      timeline.value = duration > 0 ? String(Math.round((current / duration) * 1000)) : "0";
    }
    if (currentTimeEl) {
      currentTimeEl.textContent = formatTime(current);
    }
    if (durationEl) {
      durationEl.textContent = formatTime(duration);
    }
  }

  function setVolume(value) {
    video.volume = clamp(value, 0, 1);
    video.muted = video.volume === 0;
    updateVolumeState();
  }

  function toggleMute() {
    if (video.muted || video.volume === 0) {
      video.muted = false;
      if (video.volume === 0) {
        video.volume = lastAudibleVolume || 0.5;
      }
    } else {
      lastAudibleVolume = video.volume;
      video.muted = true;
    }
    updateVolumeState();
  }

  function seekBy(seconds) {
    if (!Number.isFinite(video.duration)) {
      return;
    }
    video.currentTime = clamp(video.currentTime + seconds, 0, video.duration);
  }

  function hideAutoplayCountdown() {
    if (autoplayCountdownTimer) {
      window.clearInterval(autoplayCountdownTimer);
      autoplayCountdownTimer = null;
    }
    if (autoplayCountdown instanceof HTMLElement) {
      autoplayCountdown.hidden = true;
    }
  }

  function showAutoplayCountdown() {
    if (!nextUrl || !(autoplayInput instanceof HTMLInputElement) || !autoplayInput.checked) {
      return;
    }

    hideAutoplayCountdown();
    autoplayCountdownSeconds = 5;
    if (autoplayCountdownValue) {
      autoplayCountdownValue.textContent = String(autoplayCountdownSeconds);
    }
    if (autoplayCountdown instanceof HTMLElement) {
      autoplayCountdown.hidden = false;
    }

    autoplayCountdownTimer = window.setInterval(() => {
      autoplayCountdownSeconds -= 1;
      if (autoplayCountdownValue) {
        autoplayCountdownValue.textContent = String(Math.max(autoplayCountdownSeconds, 0));
      }
      if (autoplayCountdownSeconds <= 0) {
        hideAutoplayCountdown();
        window.location.href = nextUrl;
      }
    }, 1000);
  }

  playerArea.classList.add("is-paused");
  video.addEventListener("loadedmetadata", () => {
    playerArea.classList.remove("is-loading");
    updateTimeline();
  });
  video.addEventListener("canplay", () => playerArea.classList.remove("is-loading"));
  video.addEventListener("play", updatePlayState);
  video.addEventListener("pause", updatePlayState);
  video.addEventListener("timeupdate", updateTimeline);
  video.addEventListener("durationchange", updateTimeline);
  video.addEventListener("volumechange", updateVolumeState);
  video.addEventListener("ended", () => {
    updatePlayState();
    if (!video.loop) {
      showAutoplayCountdown();
    }
  });
  video.addEventListener("play", hideAutoplayCountdown);
  video.addEventListener("seeking", hideAutoplayCountdown);

  window.setTimeout(() => playerArea.classList.remove("is-loading"), 2500);

  playToggle?.addEventListener("click", () => {
    if (video.paused) {
      video.play();
    } else {
      video.pause();
    }
  });

  video.addEventListener("click", () => {
    if (video.paused) {
      video.play();
    } else {
      video.pause();
    }
  });

  speedSelect?.addEventListener("change", () => {
    const rate = Number(speedSelect.value);
    if (Number.isFinite(rate) && rate > 0) {
      video.playbackRate = rate;
      localStorage.setItem("localtube:speed", String(rate));
    }
  });

  timeline?.addEventListener("input", () => {
    if (!Number.isFinite(video.duration) || !(timeline instanceof HTMLInputElement)) {
      return;
    }
    video.currentTime = (Number(timeline.value) / 1000) * video.duration;
  });

  volumeInput?.addEventListener("input", () => {
    if (volumeInput instanceof HTMLInputElement) {
      setVolume(Number(volumeInput.value));
    }
  });

  autoplayInput?.addEventListener("change", () => {
    if (autoplayInput instanceof HTMLInputElement) {
      localStorage.setItem("localtube:autoplay", autoplayInput.checked ? "1" : "0");
      if (!autoplayInput.checked) {
        hideAutoplayCountdown();
      }
    }
  });

  theaterToggle?.addEventListener("click", () => {
    watchPage.classList.toggle("theater-mode");
    const enabled = watchPage.classList.contains("theater-mode");
    theaterToggle.classList.toggle("is-active", enabled);
    theaterToggle.setAttribute("aria-pressed", enabled ? "true" : "false");
    localStorage.setItem("localtube:theater", enabled ? "1" : "0");
  });

  recommendationsToggle?.addEventListener("click", () => {
    watchPage.classList.toggle("recommendations-collapsed");
    const collapsed = watchPage.classList.contains("recommendations-collapsed");
    recommendationsToggle.setAttribute("aria-pressed", collapsed ? "true" : "false");
    recommendationsToggle.setAttribute("aria-label", collapsed ? "Показать похожие видео" : "Скрыть похожие видео");
    localStorage.setItem("localtube:recommendationsCollapsed", collapsed ? "1" : "0");
  });

  fullscreenToggle?.addEventListener("click", () => {
    if (document.fullscreenElement) {
      document.exitFullscreen();
    } else {
      playerArea.requestFullscreen();
    }
  });

  playerArea.addEventListener(
    "wheel",
    (event) => {
      event.preventDefault();
      const delta = event.deltaY < 0 ? 0.05 : -0.05;
      setVolume(video.volume + delta);
    },
    { passive: false },
  );

  function seekFromArrowKey(key) {
    const now = window.performance.now();
    if (key !== lastHorizontalKey || now - lastHorizontalAt > 700) {
      horizontalPressCount = 0;
    }

    horizontalPressCount = Math.min(horizontalPressCount + 1, 3);
    lastHorizontalKey = key;
    lastHorizontalAt = now;

    const seconds = horizontalPressCount === 1 ? 5 : horizontalPressCount === 2 ? 15 : 30;
    seekBy(key === "ArrowLeft" ? -seconds : seconds);
  }

  document.addEventListener("keydown", (event) => {
    const target = event.target;
    if (target instanceof HTMLInputElement || target instanceof HTMLSelectElement || target instanceof HTMLTextAreaElement) {
      return;
    }

    if (event.key === "ArrowLeft" || event.key === "ArrowRight") {
      event.preventDefault();
      seekFromArrowKey(event.key);
    } else if (event.key === "ArrowUp") {
      event.preventDefault();
      setVolume(video.volume + 0.05);
    } else if (event.key === "ArrowDown") {
      event.preventDefault();
      setVolume(video.volume - 0.05);
    } else if (event.key === " ") {
      event.preventDefault();
      if (video.paused) {
        video.play();
      } else {
        video.pause();
      }
    } else if (event.code === "KeyM") {
      event.preventDefault();
      toggleMute();
    }
  });

  updatePlayState();
  updateVolumeState();
  updateTimeline();
}

document.addEventListener("DOMContentLoaded", initWatchPlayer);
