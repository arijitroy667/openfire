/* EngBrain site — interaction + motion layer.
   Motion (Framer's animation engine, vanilla build) is bundled in assets/vendor.
   Everything degrades to a static, fully visible page if the import fails. */

(() => {
  "use strict";

  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const canHover = window.matchMedia("(hover: hover) and (pointer: fine)").matches;
  const root = document.documentElement;
  const EASE = [0.16, 1, 0.3, 1];

  if (!reduceMotion) root.classList.add("js-anim");

  /* ---------- Basics that must work without Motion ---------- */

  const year = document.getElementById("year");
  if (year) year.textContent = String(new Date().getFullYear());

  const nav = document.getElementById("nav");
  const progress = document.getElementById("progress");

  const onScroll = () => {
    if (nav) nav.classList.toggle("is-scrolled", window.scrollY > 12);
  };

  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  const navToggle = document.getElementById("navToggle");
  const navLinks = nav && nav.querySelector(".nav__links");

  if (nav && navToggle) {
    navToggle.addEventListener("click", () => {
      const open = nav.classList.toggle("is-open");
      navToggle.setAttribute("aria-expanded", String(open));
    });

    nav.querySelectorAll(".nav__link").forEach((link) => {
      link.addEventListener("click", () => {
        nav.classList.remove("is-open");
        navToggle.setAttribute("aria-expanded", "false");
        if (navLinks) navLinks.style.display = "";
      });
    });
  }

  /* ---------- Copy buttons ---------- */

  const copyText = async (text) => {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text);
      return;
    }
    const area = document.createElement("textarea");
    area.value = text;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    document.execCommand("copy");
    document.body.removeChild(area);
  };

  document.querySelectorAll("[data-copy]").forEach((button) => {
    const label = button.querySelector("span");
    const readLabel = () => (label ? label.textContent : button.textContent);
    const writeLabel = (value) => {
      if (label) label.textContent = value;
      else button.textContent = value;
    };

    button.addEventListener("click", async () => {
      const scope = button.closest(".snippet, .code-panel");
      const target = scope ? scope.querySelector("pre code") : null;
      if (!target) return;

      const original = readLabel();
      try {
        await copyText(target.textContent.trim());
        button.classList.add("is-done");
        writeLabel("Copied");
      } catch {
        writeLabel("Press Ctrl+C");
      }
      window.setTimeout(() => {
        button.classList.remove("is-done");
        writeLabel(original);
      }, 1800);
    });
  });

  /* ---------- Command tabs ---------- */

  const tabGroups = [];
  document.querySelectorAll(".tabs").forEach((group) => {
    const tabs = Array.from(group.querySelectorAll(".tab"));
    const panel = group.parentElement.querySelector(".code-panel");
    if (!panel) return;

    const title = panel.querySelector("[data-tab-title]");
    const indicator = document.createElement("span");
    indicator.className = "tab-ind";
    indicator.setAttribute("aria-hidden", "true");
    group.prepend(indicator);

    const state = { indicator, tabs, panel, title };

    const activate = (tab) => {
      tabs.forEach((item) => {
        const active = item === tab;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-selected", String(active));
      });
      panel.querySelectorAll(".tab-pane").forEach((pane) => {
        pane.classList.toggle("is-active", pane.dataset.pane === tab.dataset.tab);
      });
      if (title) title.textContent = tab.textContent.trim().toLowerCase();
      document.dispatchEvent(new CustomEvent("engbrain:tab", { detail: state }));
    };

    tabs.forEach((tab, index) => {
      tab.addEventListener("click", () => activate(tab));
      tab.addEventListener("keydown", (event) => {
        if (event.key !== "ArrowRight" && event.key !== "ArrowLeft") return;
        event.preventDefault();
        const next = event.key === "ArrowRight" ? (index + 1) % tabs.length : (index - 1 + tabs.length) % tabs.length;
        tabs[next].focus();
        activate(tabs[next]);
      });
    });

    tabGroups.push(state);
  });

  /* ---------- Staleness demo ---------- */

  const staleTabs = Array.from(document.querySelectorAll(".stale-tab"));
  const stalePanes = Array.from(document.querySelectorAll(".stale-pane"));

  staleTabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      const level = tab.dataset.level;
      staleTabs.forEach((item) => {
        const active = item === tab;
        item.classList.toggle("is-active", active);
        item.setAttribute("aria-selected", String(active));
      });
      stalePanes.forEach((pane) => pane.classList.toggle("is-active", pane.dataset.pane === level));
      document.dispatchEvent(new CustomEvent("engbrain:stale", { detail: level }));
    });
  });

  /* ---------- Video ---------- */

  const frame = document.getElementById("videoFrame");
  const video = document.getElementById("showcaseVideo");
  const play = document.getElementById("videoPlay");

  if (frame && video && play) {
    const start = () => {
      frame.classList.add("is-playing");
      const attempt = video.play();
      if (attempt && typeof attempt.catch === "function") {
        attempt.catch(() => frame.classList.remove("is-playing"));
      }
    };
    play.addEventListener("click", start);
    video.addEventListener("click", () => {
      if (video.paused) start();
    });
    video.addEventListener("play", () => frame.classList.add("is-playing"));
    video.addEventListener("pause", () => {
      if (video.ended) frame.classList.remove("is-playing");
    });
    video.addEventListener("ended", () => frame.classList.remove("is-playing"));
    video.addEventListener("loadedmetadata", () => frame.classList.add("is-ready"));
  }

  /* ---------- Docs scroll spy ---------- */

  const sideLinks = Array.from(document.querySelectorAll(".side-link"));
  const sections = Array.from(document.querySelectorAll(".doc-section"));
  const sideRail = document.querySelector(".docs__side");

  if (sideLinks.length && sections.length && "IntersectionObserver" in window) {
    const setActive = (id, reveal) => {
      sideLinks.forEach((link) => {
        const active = link.getAttribute("href") === `#${id}`;
        link.classList.toggle("is-active", active);
        if (active && reveal && sideRail && sideRail.scrollWidth > sideRail.clientWidth + 8) {
          const left = link.offsetLeft - sideRail.clientWidth / 2 + link.offsetWidth / 2;
          sideRail.scrollTo({ left: Math.max(0, left), behavior: "smooth" });
        }
      });
    };

    const spy = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => a.boundingClientRect.top - b.boundingClientRect.top);
        if (visible.length) setActive(visible[0].target.id, true);
      },
      { rootMargin: "-16% 0px -64% 0px", threshold: 0 }
    );

    sections.forEach((section) => spy.observe(section));

    const fromHash = window.location.hash.replace("#", "");
    if (fromHash && document.getElementById(fromHash)) setActive(fromHash, false);
    else if (sideLinks[0]) setActive(sideLinks[0].getAttribute("href").replace("#", ""), false);
  }

  /* ---------- Reduced motion: show everything, stop here ---------- */

  if (reduceMotion) {
    document.querySelectorAll("[data-reveal]").forEach((el) => el.classList.add("is-visible"));
    return;
  }

  /* ---------- Motion layer ---------- */

  const revealDelay = (el) => {
    const raw = getComputedStyle(el).getPropertyValue("--delay").trim();
    const value = parseFloat(raw);
    if (!Number.isFinite(value)) return 0;
    return raw.endsWith("ms") ? value / 1000 : value;
  };

  const enter = (el, delay, M) => {
    M.animate(
      el,
      {
        opacity: [0, 1],
        transform: ["translateY(26px) scale(.985)", "translateY(0px) scale(1)"],
        filter: ["blur(9px)", "blur(0px)"],
      },
      { duration: 0.95, delay, ease: EASE }
    ).finished.then(() => {
      el.style.opacity = "";
      el.style.transform = "";
      el.style.filter = "";
      el.style.willChange = "";
      el.classList.add("is-visible");
    });
  };

  const init = (M) => {
    const { animate, inView, scroll, press, motionValue } = M;

    /* Scroll reveals, except the hero which is sequenced on load. */
    document.querySelectorAll("[data-reveal]").forEach((el) => {
      if (el.closest(".hero")) return;
      inView(el, () => enter(el, revealDelay(el), M), { margin: "0px 0px -8% 0px", amount: 0.06 });
    });

    /* Reading progress rail. */
    if (progress) scroll(animate(progress, { scaleX: [0, 1] }, { ease: "linear" }));

    /* Ambient drift for the gradient orbs. */
    document.querySelectorAll(".orb").forEach((orb, index) => {
      const distance = 24 + index * 16;
      scroll(animate(orb, { y: [-distance, distance] }, { ease: "linear" }), {
        target: document.body,
        offset: ["start start", "end end"],
      });
    });

    /* Hero: sequenced entrance, then permanent visibility. */
    const hero = document.querySelector(".hero");
    if (hero) {
      hero.querySelectorAll("[data-reveal]").forEach((el, index) => {
        el.style.opacity = "0";
        animate(
          el,
          {
            opacity: [0, 1],
            transform: ["translateY(22px) scale(.99)", "translateY(0px) scale(1)"],
            filter: ["blur(8px)", "blur(0px)"],
          },
          { duration: 1, delay: 0.06 + index * 0.075, ease: EASE }
        ).finished.then(() => {
          el.style.opacity = "";
          el.style.transform = "";
          el.style.filter = "";
          el.classList.add("is-visible");
        });
      });

      hero.querySelectorAll(".hero__badge").forEach((badge, index) => {
        animate(
          badge,
          { y: [0, -9, 0], rotate: [0, index ? -1.2 : 1.2, 0] },
          { duration: 7 + index * 1.6, repeat: Infinity, ease: "easeInOut" }
        );
      });
    }

    /* Terminal parallax tilt, spring-smoothed through motion values. */
    const art = document.querySelector(".hero__art");
    const terminal = art && art.querySelector(".terminal");
    if (art && terminal && canHover) {
      const rx = motionValue(0);
      const ry = motionValue(0);
      const paint = () => {
        terminal.style.transform = `perspective(1200px) rotateX(${rx.get()}deg) rotateY(${ry.get()}deg) rotateZ(-1.1deg) scale(1.01)`;
      };
      rx.on("change", paint);
      ry.on("change", paint);

      art.addEventListener("pointermove", (event) => {
        const rect = art.getBoundingClientRect();
        const px = (event.clientX - rect.left) / rect.width - 0.5;
        const py = (event.clientY - rect.top) / rect.height - 0.5;
        animate(rx, -py * 6, { type: "spring", stiffness: 140, damping: 20 });
        animate(ry, px * 8, { type: "spring", stiffness: 140, damping: 20 });
      });

      art.addEventListener("pointerleave", () => {
        animate(rx, 0, { type: "spring", stiffness: 120, damping: 18 });
        animate(ry, 0, { type: "spring", stiffness: 120, damping: 18 });
      });
    }

    /* Card spotlight. */
    if (canHover) {
      document.querySelectorAll(".card").forEach((card) => {
        card.addEventListener("pointermove", (event) => {
          const rect = card.getBoundingClientRect();
          card.style.setProperty("--mx", `${event.clientX - rect.left}px`);
          card.style.setProperty("--my", `${event.clientY - rect.top}px`);
        });
      });
    }

    /* Springy press feedback. */
    document.querySelectorAll(".btn, .video-play, .tab, .stale-tab, .copy").forEach((el) => {
      press(el, () => {
        animate(el, { scale: 0.965 }, { duration: 0.14, ease: EASE });
        return () => animate(el, { scale: 1 }, { type: "spring", stiffness: 420, damping: 26 });
      });
    });

    /* Command tabs: sliding indicator + pane crossfade. */
    tabGroups.forEach((state) => {
      const place = () => {
        const active = state.tabs.find((tab) => tab.classList.contains("is-active"));
        if (!active) return;
        animate(
          state.indicator,
          { x: active.offsetLeft, width: active.offsetWidth, opacity: 1 },
          { duration: 0.45, ease: EASE }
        );
      };

      place();
      window.addEventListener("resize", place, { passive: true });
      if (document.fonts && document.fonts.ready) document.fonts.ready.then(place);
      document.addEventListener("engbrain:tab", (event) => {
        if (event.detail !== state) return;
        place();
        const pane = state.panel.querySelector(".tab-pane.is-active");
        if (pane) {
          animate(
            pane,
            { opacity: [0, 1], transform: ["translateY(7px)", "translateY(0px)"] },
            { duration: 0.4, ease: EASE }
          );
        }
      });
    });

    /* Staleness pane fade. */
    document.addEventListener("engbrain:stale", () => {
      const pane = document.querySelector(".stale-pane.is-active");
      if (!pane) return;
      animate(
        pane,
        { opacity: [0, 1], transform: ["translateY(6px)", "translateY(0px)"] },
        { duration: 0.34, ease: EASE }
      );
    });

    /* Number count-up. */
    document.querySelectorAll("[data-count]").forEach((el) => {
      const raw = el.textContent.trim();
      const target = Number(el.dataset.count);
      if (!Number.isFinite(target) || !/^\d+$/.test(raw)) return;
      el.textContent = "0";
      inView(
        el,
        () => {
          animate(0, target, {
            duration: 1.25,
            ease: EASE,
            onUpdate: (value) => {
              el.textContent = String(Math.round(value));
            },
          });
        },
        { amount: 0.6 }
      );
    });

    /* Headings drift slightly against the scroll. */
    document.querySelectorAll(".section-head h2").forEach((heading) => {
      scroll(animate(heading, { y: [12, -12] }, { ease: "linear" }), {
        target: heading,
        offset: ["start end", "end start"],
      });
    });

    /* Docs hero entrance. */
    const docHero = document.querySelector(".doc-hero");
    if (docHero) {
      docHero.querySelectorAll(":scope > *").forEach((el, index) => {
        animate(
          el,
          { opacity: [0, 1], transform: ["translateY(18px)", "translateY(0px)"], filter: ["blur(7px)", "blur(0px)"] },
          { duration: 0.9, delay: 0.05 + index * 0.08, ease: EASE }
        ).finished.then(() => {
          el.style.filter = "";
          el.style.transform = "";
          el.style.opacity = "";
        });
      });
    }

    /* Mobile nav dropdown. */
    if (nav && navToggle && navLinks) {
      navToggle.addEventListener("click", () => {
        if (nav.classList.contains("is-open") && window.innerWidth <= 960) {
          navLinks.style.display = "flex";
          animate(
            navLinks,
            { opacity: [0, 1], transform: ["translateY(-10px) scale(.98)", "translateY(0) scale(1)"] },
            { duration: 0.34, ease: EASE }
          );
        } else {
          navLinks.style.display = "";
        }
      });
    }
  };

  import("./vendor/motion.js")
    .then((M) => init(M))
    .catch((error) => {
      console.error("[engbrain] motion init failed:", error);
      root.classList.remove("js-anim");
      document.querySelectorAll("[data-reveal]").forEach((el) => el.classList.add("is-visible"));
    });
})();
