function initShellPreferences() {
  const themeToggle = document.querySelector("[data-theme-toggle]");
  const sidebarToggle = document.querySelector("[data-sidebar-toggle]");
  const savedTheme = localStorage.getItem("videocloud:theme") || "light";
  const savedSidebar = localStorage.getItem("videocloud:sidebarCollapsed") === "1";

  function applyTheme(theme) {
    const normalizedTheme = theme === "dark" ? "dark" : "light";
    document.documentElement.dataset.theme = normalizedTheme;
    document.body.dataset.theme = normalizedTheme;
    if (themeToggle) {
      const isDark = normalizedTheme === "dark";
      themeToggle.setAttribute("aria-pressed", isDark ? "true" : "false");
      themeToggle.setAttribute("aria-label", isDark ? "Увімкнути світлу тему" : "Увімкнути темну тему");
      themeToggle.setAttribute("title", isDark ? "Увімкнути світлу тему" : "Увімкнути темну тему");
    }
  }

  applyTheme(savedTheme);
  document.body.classList.toggle("sidebar-collapsed", savedSidebar);
  if (sidebarToggle) {
    sidebarToggle.setAttribute("aria-pressed", savedSidebar ? "true" : "false");
    sidebarToggle.setAttribute("aria-label", savedSidebar ? "Показати меню" : "Сховати меню");
    sidebarToggle.setAttribute("title", savedSidebar ? "Показати меню" : "Сховати меню");
  }

  themeToggle?.addEventListener("click", () => {
    const nextTheme = document.body.dataset.theme === "dark" ? "light" : "dark";
    localStorage.setItem("videocloud:theme", nextTheme);
    applyTheme(nextTheme);
  });

  sidebarToggle?.addEventListener("click", () => {
    const collapsed = !document.body.classList.contains("sidebar-collapsed");
    document.body.classList.toggle("sidebar-collapsed", collapsed);
    localStorage.setItem("videocloud:sidebarCollapsed", collapsed ? "1" : "0");
    sidebarToggle.setAttribute("aria-pressed", collapsed ? "true" : "false");
    sidebarToggle.setAttribute("aria-label", collapsed ? "Показати меню" : "Сховати меню");
    sidebarToggle.setAttribute("title", collapsed ? "Показати меню" : "Сховати меню");
  });
}

function initAccountMenu() {
  const menu = document.querySelector("[data-account-menu]");
  const toggle = menu?.querySelector("[data-account-menu-toggle]");
  if (!(menu instanceof HTMLElement) || !(toggle instanceof HTMLButtonElement)) {
    return;
  }

  function setOpen(open) {
    menu.classList.toggle("is-open", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
  }

  toggle.addEventListener("click", (event) => {
    event.stopPropagation();
    setOpen(!menu.classList.contains("is-open"));
  });

  document.addEventListener("click", (event) => {
    if (!menu.contains(event.target)) {
      setOpen(false);
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") {
      setOpen(false);
      toggle.focus();
    }
  });
}

function readVideoProgress(element) {
  if (!(element instanceof HTMLElement)) {
    return null;
  }

  const current = Number(element.dataset.progressCurrent || 0);
  const duration = Number(element.dataset.progressDuration || 0);
  if (!Number.isFinite(current) || !Number.isFinite(duration) || duration <= 0 || current <= 0) {
    return null;
  }
  return { current, duration };
}

function postVideoProgress(videoId, current, duration, useBeacon = false) {
  if (!videoId || !Number.isFinite(current) || !Number.isFinite(duration) || duration <= 0) {
    return;
  }

  const data = new FormData();
  data.set("current_seconds", String(Math.round(clamp(current, 0, duration))));
  data.set("duration_seconds", String(Math.round(duration)));

  if (useBeacon && navigator.sendBeacon) {
    navigator.sendBeacon(`/videos/${videoId}/progress`, data);
    return;
  }

  fetch(`/videos/${videoId}/progress`, {
    method: "POST",
    body: data,
    headers: {
      "X-Requested-With": "XMLHttpRequest",
      "Accept": "application/json",
    },
    keepalive: true,
  }).catch((error) => console.warn(error));
}

function initVideoCards() {
  document.querySelectorAll("[data-video-card]").forEach((card) => {
    const progress = readVideoProgress(card);
    const bar = card.querySelector("[data-video-progress] b");
    if (progress && bar instanceof HTMLElement) {
      const percent = clamp((progress.current / progress.duration) * 100, 0, 100);
      card.classList.toggle("has-progress", percent > 1);
      bar.style.width = `${percent}%`;
    }

    const preview = card.querySelector("[data-preview-video]");
    if (!(preview instanceof HTMLVideoElement)) {
      return;
    }

    let hoverTimer = 0;
    let previewProgressApplied = false;

    preview.addEventListener("loadedmetadata", () => {
      if (!previewProgressApplied && progress && progress.current > 3 && progress.duration > 0) {
        preview.currentTime = clamp(progress.current, 0, Math.max(0, preview.duration - 2));
        previewProgressApplied = true;
      }
    });

    function stopPreview() {
      window.clearTimeout(hoverTimer);
      card.classList.remove("is-previewing");
      preview.pause();
    }

    card.addEventListener("mouseenter", () => {
      hoverTimer = window.setTimeout(() => {
        if (!preview.src) {
          preview.src = preview.dataset.previewSrc || "";
        }
        preview.play().then(() => {
          card.classList.add("is-previewing");
        }).catch(() => {
          card.classList.remove("is-previewing");
        });
      }, 260);
    });

    card.addEventListener("mouseleave", stopPreview);
    card.addEventListener("focusout", (event) => {
      if (!card.contains(event.relatedTarget)) {
        stopPreview();
      }
    });
  });
}

function initShareButtons() {
  document.querySelectorAll("[data-share-button]").forEach((button) => {
    button.addEventListener("click", async () => {
      const url = button.dataset.shareUrl || window.location.href;
      try {
        if (navigator.share) {
          await navigator.share({ title: document.title, url });
        } else if (navigator.clipboard) {
          await navigator.clipboard.writeText(url);
          button.textContent = "Посилання скопійовано";
          window.setTimeout(() => {
            button.textContent = "Поділитися";
          }, 1600);
        }
      } catch (error) {
        console.warn(error);
      }
    });
  });
}

async function submitAjaxForm(form, submitter) {
  const data = new FormData(form);
  const response = await fetch(form.action, {
    method: form.method || "POST",
    body: data,
    headers: {
      "X-Requested-With": "XMLHttpRequest",
      "Accept": "application/json",
    },
  });
  if (!response.ok) {
    throw new Error(`Request failed: ${response.status}`);
  }
  return response.json();
}

function setButtonBusy(button, busy) {
  if (!(button instanceof HTMLButtonElement)) {
    return;
  }
  button.disabled = busy;
}

function playButtonAnimation(button) {
  if (!(button instanceof HTMLElement)) {
    return;
  }
  button.classList.remove("is-feedback");
  void button.offsetWidth;
  button.classList.add("is-feedback");
}

function playCommentAnimation(comment) {
  comment.classList.add("is-new");
  window.setTimeout(() => {
    comment.classList.remove("is-new");
  }, 700);
}

function createCommentElement(comment) {
  const article = document.createElement("article");
  article.className = "comment";
  article.dataset.commentId = String(comment.id);

  const head = document.createElement("div");
  head.className = "comment-head";

  const authorBlock = document.createElement("span");
  const author = document.createElement("strong");
  author.textContent = comment.username;
  const createdAt = document.createElement("small");
  createdAt.textContent = comment.created_at;
  authorBlock.append(author, createdAt);
  head.append(authorBlock);

  if (comment.can_delete) {
    const deleteForm = document.createElement("form");
    deleteForm.action = `/comments/${comment.id}/delete`;
    deleteForm.method = "post";
    deleteForm.dataset.confirm = "Видалити коментар?";
    deleteForm.dataset.commentDeleteForm = "";
    const deleteButton = document.createElement("button");
    deleteButton.type = "submit";
    deleteButton.className = "button ghost small-button";
    deleteButton.textContent = "Видалити";
    deleteForm.append(deleteButton);
    head.append(deleteForm);
  }

  const body = document.createElement("p");
  body.textContent = comment.body;
  article.append(head, body);
  return article;
}

function resizeTextareaToContent(textarea) {
  textarea.style.height = "auto";
  textarea.style.height = `${textarea.scrollHeight}px`;
}

function initWatchAjaxActions() {
  const watchPage = document.querySelector("[data-watch-page]");
  if (!watchPage) {
    return;
  }

  watchPage.querySelectorAll("[data-reaction-form]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      const button = event.submitter;
      setButtonBusy(button, true);
      try {
        const result = await submitAjaxForm(form, button);
        const likeButton = watchPage.querySelector("[data-like-button]");
        const dislikeButton = watchPage.querySelector("[data-dislike-button]");
        const likeCount = watchPage.querySelector("[data-like-count]");
        const dislikeCount = watchPage.querySelector("[data-dislike-count]");
        if (likeCount) {
          likeCount.textContent = String(result.likes_count);
        }
        if (dislikeCount) {
          dislikeCount.textContent = String(result.dislikes_count);
        }
        likeButton?.classList.toggle("primary", result.user_reaction === 1);
        dislikeButton?.classList.toggle("primary", result.user_reaction === -1);
        playButtonAnimation(button);
      } catch (error) {
        console.warn(error);
      } finally {
        setButtonBusy(button, false);
      }
    });
  });

  watchPage.querySelectorAll("[data-watch-later-form]").forEach((form) => {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      event.stopPropagation();
      const button = event.submitter;
      setButtonBusy(button, true);
      try {
        const result = await submitAjaxForm(form, button);
        if (button instanceof HTMLButtonElement) {
          button.setAttribute("aria-label", result.label);
          button.setAttribute("title", result.label);
          button.classList.toggle("primary", Boolean(result.in_watch_later));
        }
      } catch (error) {
        console.warn(error);
      } finally {
        setButtonBusy(button, false);
      }
    });
  });

  const commentForm = watchPage.querySelector("[data-comment-form]");
  const commentTextarea = commentForm?.querySelector("textarea");
  if (commentTextarea instanceof HTMLTextAreaElement) {
    resizeTextareaToContent(commentTextarea);
    commentTextarea.addEventListener("input", () => resizeTextareaToContent(commentTextarea));
  }

  commentForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    event.stopPropagation();
    const form = event.currentTarget;
    const button = event.submitter;
    if (!(form instanceof HTMLFormElement)) {
      return;
    }
    setButtonBusy(button, true);
    try {
      const result = await submitAjaxForm(form, button);
      const list = watchPage.querySelector("[data-comment-list]");
      const empty = watchPage.querySelector("[data-empty-comments]");
      if (list && result.comment) {
        const comment = createCommentElement(result.comment);
        list.append(comment);
        playCommentAnimation(comment);
      }
      if (empty instanceof HTMLElement) {
        empty.hidden = true;
      }
      form.reset();
      const textarea = form.querySelector("textarea");
      if (textarea instanceof HTMLTextAreaElement) {
        resizeTextareaToContent(textarea);
        textarea.focus();
      }
    } catch (error) {
      console.warn(error);
    } finally {
      setButtonBusy(button, false);
    }
  });

  watchPage.addEventListener("submit", async (event) => {
    const form = event.target;
    if (!(form instanceof HTMLFormElement) || form.dataset.commentDeleteForm !== "") {
      return;
    }
    const confirmation = form.dataset.confirm;
    if (confirmation && !window.confirm(confirmation)) {
      event.preventDefault();
      event.stopPropagation();
      return;
    }
    event.preventDefault();
    event.stopPropagation();
    const button = event.submitter;
    setButtonBusy(button, true);
    try {
      const result = await submitAjaxForm(form, button);
      const comment = watchPage.querySelector(`[data-comment-id="${result.comment_id}"]`);
      comment?.remove();
      const list = watchPage.querySelector("[data-comment-list]");
      const empty = watchPage.querySelector("[data-empty-comments]");
      if (empty instanceof HTMLElement && list && !list.querySelector(".comment")) {
        empty.hidden = false;
      }
    } catch (error) {
      console.warn(error);
    } finally {
      setButtonBusy(button, false);
    }
  });
}

document.addEventListener("submit", (event) => {
  const form = event.target;
  if (!(form instanceof HTMLFormElement)) {
    return;
  }

  const confirmation = form.dataset.confirm;
  if (confirmation && !window.confirm(confirmation)) {
    event.preventDefault();
    return;
  }

  if (form.dataset.deleteVideo === "" && form.dataset.deleteReady !== "1") {
    event.preventDefault();
    const player = document.querySelector("[data-player]");
    if (player instanceof HTMLVideoElement) {
      player.pause();
      player.removeAttribute("src");
      player.querySelectorAll("source").forEach((source) => source.removeAttribute("src"));
      player.load();
    }

    const submitter = event.submitter;
    if (submitter instanceof HTMLButtonElement) {
      submitter.disabled = true;
      submitter.dataset.originalText = submitter.textContent || "";
      submitter.textContent = "Видалення...";
    }

    window.setTimeout(() => {
      form.dataset.deleteReady = "1";
      form.submit();
    }, 300);
    return;
  }

  if (form.dataset.uploadForm === "" && form.dataset.submitReady !== "1") {
    event.preventDefault();
    form.classList.add("is-uploading");

    const submitter = event.submitter;
    if (submitter instanceof HTMLButtonElement) {
      submitter.disabled = true;
      submitter.dataset.originalText = submitter.textContent || "";
      submitter.textContent = "Завантаження...";
    }

    const minSubmitMs = Number(form.dataset.minSubmitMs || 1000);
    window.setTimeout(() => {
      form.dataset.submitReady = "1";
      form.submit();
    }, Number.isFinite(minSubmitMs) ? Math.max(minSubmitMs, 1000) : 1000);
    return;
  }

  const submitter = event.submitter;
  if (submitter instanceof HTMLButtonElement) {
    submitter.disabled = true;
    submitter.dataset.originalText = submitter.textContent || "";
    submitter.textContent = "Зачекайте...";
  }
});

function initDropzones() {
  document.querySelectorAll("[data-dropzone]").forEach((dropzone) => {
    const input = dropzone.querySelector('input[type="file"]');
    const fileName = dropzone.querySelector("[data-dropzone-name]");
    const maxFileBaseLength = 16;
    if (!(input instanceof HTMLInputElement)) {
      return;
    }

    function shortenFileName(name) {
      const dotIndex = name.lastIndexOf(".");
      const extension = dotIndex > 0 ? name.slice(dotIndex) : "";
      const baseName = dotIndex > 0 ? name.slice(0, dotIndex) : name;
      if (baseName.length <= maxFileBaseLength) {
        return name;
      }
      return `${baseName.slice(0, maxFileBaseLength)}...${extension}`;
    }

    function showFileName() {
      if (fileName) {
        const selectedName = input.files?.[0]?.name || "";
        fileName.textContent = selectedName ? shortenFileName(selectedName) : "або виберіть файл";
        if (selectedName) {
          fileName.setAttribute("title", selectedName);
        } else {
          fileName.removeAttribute("title");
        }
      }
      dropzone.classList.toggle("has-file", Boolean(input.files?.length));
    }

    dropzone.addEventListener("dragover", (event) => {
      event.preventDefault();
      dropzone.classList.add("is-dragover");
    });

    dropzone.addEventListener("dragleave", () => {
      dropzone.classList.remove("is-dragover");
    });

    dropzone.addEventListener("drop", (event) => {
      event.preventDefault();
      dropzone.classList.remove("is-dragover");
      if (event.dataTransfer?.files?.length) {
        input.files = event.dataTransfer.files;
        showFileName();
      }
    });

    input.addEventListener("change", showFileName);
  });
}

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
  const videoId = watchPage.dataset.videoId || "";
  let lastHorizontalKey = "";
  let lastHorizontalAt = 0;
  let horizontalPressCount = 0;
  let lastAudibleVolume = 1;
  let autoplayCountdownTimer = null;
  let autoplayCountdownSeconds = 5;

  if (!(video instanceof HTMLVideoElement) || !playerArea) {
    return;
  }

  const savedTheater = localStorage.getItem("videocloud:theater") === "1";
  const savedCollapsed = localStorage.getItem("videocloud:recommendationsCollapsed") === "1";
  const savedAutoplay = localStorage.getItem("videocloud:autoplay") === "1";
  const savedVolume = Number(localStorage.getItem("videocloud:volume"));
  const savedSpeed = Number(localStorage.getItem("videocloud:speed"));

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

  const savedProgress = readVideoProgress(watchPage);
  let restoredProgress = false;
  let lastProgressSaveAt = 0;

  function updatePlayState() {
    if (playToggle) {
      playToggle.textContent = video.paused ? "▶" : "Ⅱ";
      playToggle.setAttribute("aria-label", video.paused ? "Відтворити" : "Пауза");
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
    localStorage.setItem("videocloud:volume", String(video.volume));
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

  function saveCurrentProgress(force = false, useBeacon = false) {
    if (!Number.isFinite(video.duration) || video.duration <= 0) {
      return;
    }

    const now = window.performance.now();
    if (!force && now - lastProgressSaveAt < 5000) {
      return;
    }

    lastProgressSaveAt = now;
    postVideoProgress(videoId, video.currentTime, video.duration, useBeacon);
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
    if (!restoredProgress && savedProgress && savedProgress.current > 3 && savedProgress.duration > 0) {
      video.currentTime = clamp(savedProgress.current, 0, Math.max(0, video.duration - 2));
      restoredProgress = true;
    }
    updateTimeline();
  });
  video.addEventListener("canplay", () => playerArea.classList.remove("is-loading"));
  video.addEventListener("play", updatePlayState);
  video.addEventListener("pause", updatePlayState);
  video.addEventListener("timeupdate", updateTimeline);
  video.addEventListener("timeupdate", () => saveCurrentProgress(false));
  video.addEventListener("pause", () => saveCurrentProgress(true));
  video.addEventListener("ended", () => saveCurrentProgress(true));
  window.addEventListener("pagehide", () => saveCurrentProgress(true, true));
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
      localStorage.setItem("videocloud:speed", String(rate));
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
      localStorage.setItem("videocloud:autoplay", autoplayInput.checked ? "1" : "0");
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
    localStorage.setItem("videocloud:theater", enabled ? "1" : "0");
  });

  recommendationsToggle?.addEventListener("click", () => {
    watchPage.classList.toggle("recommendations-collapsed");
    const collapsed = watchPage.classList.contains("recommendations-collapsed");
    recommendationsToggle.setAttribute("aria-pressed", collapsed ? "true" : "false");
    recommendationsToggle.setAttribute("aria-label", collapsed ? "Показати інші відео" : "Сховати інші відео");
    localStorage.setItem("videocloud:recommendationsCollapsed", collapsed ? "1" : "0");
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

document.addEventListener("DOMContentLoaded", () => {
  initShellPreferences();
  initAccountMenu();
  initShareButtons();
  initDropzones();
  initVideoCards();
  initWatchAjaxActions();
  initWatchPlayer();
});
