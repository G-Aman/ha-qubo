/**
 * Qubo PTZ Joystick Card - Custom Lovelace card for camera PTZ control.
 *
 * Install: copy to /config/www/qubo-ptz-joystick.js
 * Add as resource: Settings → Dashboards → Resources → /local/qubo-ptz-joystick.js (JS Module)
 *
 * Usage in Lovelace:
 *   type: custom:qubo-ptz-joystick
 *   entity: camera.qubo_camera_<uuid>   (any entity from the camera device)
 *   device_id: <device_uuid>            (the Qubo device UUID)
 *   name: Camera PTZ                    (optional)
 *   size: 200                           (optional, default 200px)
 */

class QuboPtzJoystick extends HTMLElement {
  static get properties() {
    return {
      hass: {},
      config: {},
    };
  }

  set hass(hass) {
    this._hass = hass;
    this._updateState();
  }

  setConfig(config) {
    if (!config.entity) {
      throw new Error("entity is required");
    }
    if (!config.device_id) {
      throw new Error("device_id is required (Qubo device UUID)");
    }
    this._config = config;
    this._size = config.size || 200;
    this._render();
  }

  getCardSize() {
    return 3;
  }

  _updateState() {
    if (!this._hass || !this._config) return;
    const entity = this._hass.states[this._config.entity];
    if (entity) {
      const label = this.shadowRoot?.querySelector(".state-label");
      if (label) {
        label.textContent = entity.state === "idle" ? "Ready" : entity.state;
      }
    }
  }

  _render() {
    if (!this.shadowRoot) {
      this.attachShadow({ mode: "open" });
    }

    const size = this._size;
    const center = size / 2;
    const outerR = size / 2 - 4;
    const innerR = outerR * 0.35;
    const btnR = outerR * 0.22;
    const btnDist = (outerR + innerR) / 2;

    // Direction button positions (UP, RIGHT, DOWN, LEFT)
    const dirs = [
      { name: "UP", label: "▲", x: center, y: center - btnDist, angle: -90 },
      { name: "RIGHT", label: "▶", x: center + btnDist, y: center, angle: 0 },
      { name: "DOWN", label: "▼", x: center, y: center + btnDist, angle: 90 },
      { name: "LEFT", label: "◀", x: center - btnDist, y: center, angle: 180 },
    ];

    const btns = dirs
      .map(
        (d) => `
      <circle
        class="ptz-btn"
        data-direction="${d.name}"
        cx="${d.x}"
        cy="${d.y}"
        r="${btnR}"
        fill="var(--ptz-btn-bg, rgba(255,255,255,0.08))"
        stroke="var(--ptz-btn-stroke, rgba(255,255,255,0.2))"
        stroke-width="1.5"
        style="cursor: pointer;"
      />
      <text
        class="ptz-icon"
        data-direction="${d.name}"
        x="${d.x}"
        y="${d.y}"
        text-anchor="middle"
        dominant-baseline="central"
        fill="var(--ptz-icon-color, rgba(255,255,255,0.7))"
        font-size="${btnR * 0.85}"
        style="pointer-events: none; user-select: none;"
      >${d.label}</text>
    `
      )
      .join("");

    this.shadowRoot.innerHTML = `
      <style>
        :host {
          display: block;
        }
        ha-card {
          padding: 16px;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 8px;
        }
        .card-header {
          font-size: 14px;
          font-weight: 500;
          color: var(--primary-text-color);
          align-self: flex-start;
        }
        .joystick-container {
          position: relative;
          width: ${size}px;
          height: ${size}px;
        }
        svg {
          display: block;
        }
        .outer-ring {
          fill: var(--ptz-ring-bg, rgba(0,0,0,0.2));
          stroke: var(--ptz-ring-stroke, rgba(255,255,255,0.1));
          stroke-width: 2;
        }
        .inner-circle {
          fill: var(--ptz-center-bg, var(--card-background-color, #1c1c1c));
          stroke: var(--ptz-ring-stroke, rgba(255,255,255,0.1));
          stroke-width: 1.5;
        }
        .ptz-btn {
          transition: fill 0.1s ease;
        }
        .ptz-btn:hover {
          fill: var(--ptz-btn-hover, rgba(255,255,255,0.15));
        }
        .ptz-btn.active {
          fill: var(--ptz-btn-active, var(--accent-color, #03a9f4));
          stroke: var(--ptz-btn-active-stroke, var(--accent-color, #03a9f4));
        }
        .home-btn {
          cursor: pointer;
          transition: fill 0.1s ease;
        }
        .home-btn:hover {
          fill: var(--ptz-btn-hover, rgba(255,255,255,0.15));
        }
        .state-label {
          font-size: 12px;
          color: var(--secondary-text-color);
          text-align: center;
        }
      </style>
      <ha-card>
        <div class="card-header">${this._config?.name || "PTZ Control"}</div>
        <div class="joystick-container">
          <svg width="${size}" height="${size}" viewBox="0 0 ${size} ${size}">
            <!-- Outer ring -->
            <circle
              class="outer-ring"
              cx="${center}"
              cy="${center}"
              r="${outerR}"
            />
            <!-- Center circle (home button) -->
            <circle
              class="home-btn inner-circle"
              cx="${center}"
              cy="${center}"
              r="${innerR}"
              data-direction="HOME"
            />
            <text
              x="${center}"
              y="${center}"
              text-anchor="middle"
              dominant-baseline="central"
              fill="var(--secondary-text-color)"
              font-size="${innerR * 0.7}"
              style="pointer-events: none; user-select: none;"
            >⌂</text>
            <!-- Direction buttons -->
            ${btns}
          </svg>
        </div>
        <div class="state-label">Ready</div>
      </ha-card>
    `;

    this._attachEvents();
  }

  _attachEvents() {
    const svg = this.shadowRoot.querySelector("svg");
    if (!svg) return;

    // Track active state for visual feedback
    const setActive = (direction, active) => {
      const btns = this.shadowRoot.querySelectorAll(
        `.ptz-btn[data-direction="${direction}"]`
      );
      btns.forEach((btn) => {
        if (active) {
          btn.classList.add("active");
        } else {
          btn.classList.remove("active");
        }
      });
    };

    // Pointer down on direction buttons — start continuous movement
    svg.addEventListener("pointerdown", (e) => {
      const btn = e.target.closest("[data-direction]");
      if (!btn) return;
      const direction = btn.dataset.direction;

      if (direction === "HOME") {
        // Home = single move to 0,0
        this._callService("camera_ptz_move", { h: 0, v: 0 });
        return;
      }

      setActive(direction, true);
      this._callService("camera_ptz_start_pan", { direction });
      e.preventDefault();
    });

    // Pointer up / leave — stop movement
    const stopAll = () => {
      ["UP", "DOWN", "LEFT", "RIGHT"].forEach((d) => setActive(d, false));
      this._callService("camera_ptz_stop_pan");
    };

    svg.addEventListener("pointerup", stopAll);
    svg.addEventListener("pointerleave", stopAll);
    svg.addEventListener("pointercancel", stopAll);

    // Also handle context menu (long press on mobile)
    svg.addEventListener("contextmenu", (e) => e.preventDefault());
  }

  _callService(service, data = {}) {
    if (!this._hass || !this._config) return;
    this._hass.callService("qubo", service, {
      device_id: this._config.device_id,
      ...data,
    });
  }

  // Boilerplate HA card interface
  get hass() {
    return this._hass;
  }
}

customElements.define("qubo-ptz-joystick", QuboPtzJoystick);

// Register with HA card picker
window.customCards = window.customCards || [];
window.customCards.push({
  type: "qubo-ptz-joystick",
  name: "Qubo PTZ Joystick",
  description: "Round directional pad for Qubo camera PTZ control",
});
