---
name: Cybercrime Intelligence Command Center
colors:
  surface: '#101418'
  surface-dim: '#101418'
  surface-bright: '#36393e'
  surface-container-lowest: '#0b0f13'
  surface-container-low: '#181c20'
  surface-container: '#1c2024'
  surface-container-high: '#272a2f'
  surface-container-highest: '#31353a'
  on-surface: '#e0e2e9'
  on-surface-variant: '#bac9cc'
  inverse-surface: '#e0e2e9'
  inverse-on-surface: '#2d3136'
  outline: '#849396'
  outline-variant: '#3b494c'
  surface-tint: '#00daf3'
  primary: '#c3f5ff'
  on-primary: '#00363d'
  primary-container: '#00e5ff'
  on-primary-container: '#00626e'
  inverse-primary: '#006875'
  secondary: '#4cd6fb'
  on-secondary: '#003642'
  secondary-container: '#00b2d6'
  on-secondary-container: '#003f4e'
  tertiary: '#ffe9d3'
  on-tertiary: '#472a00'
  tertiary-container: '#ffc681'
  on-tertiary-container: '#7e4e00'
  error: '#ffb4ab'
  on-error: '#690005'
  error-container: '#93000a'
  on-error-container: '#ffdad6'
  primary-fixed: '#9cf0ff'
  primary-fixed-dim: '#00daf3'
  on-primary-fixed: '#001f24'
  on-primary-fixed-variant: '#004f58'
  secondary-fixed: '#b3ebff'
  secondary-fixed-dim: '#4cd6fb'
  on-secondary-fixed: '#001f27'
  on-secondary-fixed-variant: '#004e5f'
  tertiary-fixed: '#ffddb8'
  tertiary-fixed-dim: '#ffb95f'
  on-tertiary-fixed: '#2a1700'
  on-tertiary-fixed-variant: '#653e00'
  background: '#101418'
  on-background: '#e0e2e9'
  surface-variant: '#31353a'
typography:
  headline-xl:
    fontFamily: Space Grotesk
    fontSize: 32px
    fontWeight: '700'
    lineHeight: 40px
    letterSpacing: -0.02em
  headline-xl-mobile:
    fontFamily: Space Grotesk
    fontSize: 24px
    fontWeight: '700'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-lg:
    fontFamily: Space Grotesk
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Space Grotesk
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 24px
    letterSpacing: 0em
  body-lg:
    fontFamily: Inter
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 24px
    letterSpacing: 0em
  body-md:
    fontFamily: Inter
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 20px
    letterSpacing: 0em
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 18px
    letterSpacing: 0.01em
  mono-data-lg:
    fontFamily: JetBrains Mono
    fontSize: 16px
    fontWeight: '600'
    lineHeight: 22px
    letterSpacing: -0.01em
  mono-data-md:
    fontFamily: JetBrains Mono
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 18px
    letterSpacing: 0em
  mono-data-sm:
    fontFamily: JetBrains Mono
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.02em
  label-caps:
    fontFamily: JetBrains Mono
    fontSize: 10px
    fontWeight: '600'
    lineHeight: 14px
    letterSpacing: 0.08em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 0.75rem
  margin: 1rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1.25rem
  space-xl: 1.75rem
---

## Brand & Style

This design system embodies a high-stakes, mission-critical operations environment engineered for cyber threat intelligence, threat actor tracking, incident telemetry, and forensic analysis. The aesthetic fuses **Technical Brutalism** with **Modern Analytical Glass**, prioritizing rapid data parsing, high density, and absolute clarity under cognitive pressure.

### Core Visual Principles
- **Tactical Precision:** Zero visual fluff. Interfaces rely on structured coordinate grids, technical line art, monospace data anchors, and compartmentalized modules.
- **Instrument-Grade Contrast:** Deep slate surfaces minimize visual fatigue during prolonged watch-floor shifts, while electric cyan accents guide the eye instantaneously to active incidents, selected nodes, and system vectors.
- **Restrained Phosphor Radiance:** Accent glows are strictly functional—reserved for active intercepts, anomalous indicators, or real-time status changes.
- **Hierarchical Telemetry:** Data is treated as physical signal intelligence. Metadata (timestamps, UUIDs, IPv6 blocks, CVE tags) retains a persistent, machine-readable identity.

## Colors

The color palette establishes an uncompromising dark field optimized for high-resolution security operations center (SOC) video walls and dual-display analyst workstations. 

### Palette Architecture
- **Base Canvas (`#05080C`):** Deepest charcoal-void, anchoring background space and canvas margins.
- **Primary Panel (`#0B1117`):** Elevated structural background for analytical cards, graphs, and tactical consoles.
- **Secondary Panel (`#101820`):** Surface tone for sub-panels, modal drawers, toolbars, and grouped metadata pods.
- **Technical Borders (`#1C2935`):** Structural 1px boundary lines ensuring clean module separation without visual clutter.
- **Primary Focus / Cyan (`#00E5FF`):** Signal accent for primary telemetry, selected graph nodes, interactive active states, and focal metrics.
- **Secondary Accent / Electric Blue (`#00B4D8`):** Informational highlights, link routes, and auxiliary graph vectors.
- **Threat Critical / Crimson (`#EF4444`):** High-risk incidents, zero-day indicators, kill-chain progression, and destructive actions.
- **Threat Alert / Amber (`#F59E0B`):** Warnings, active investigations, unverified signatures, and anomalous thresholds.
- **System Nominal / Emerald (`#10B981`):** Verified cryptographic handshakes, secure pipelines, resolved anomalies.
- **Foreground Cool Gray (`#94A3B8`) & Pure Signal White (`#E2E8F0`):** Structural hierarchy for tabular telemetry, data labels, and primary values.

## Typography

The typographic hierarchy divides cognitive responsibilities into two tracks: human-speed scanning via **Inter** and **Space Grotesk**, and machine-speed parsing via **JetBrains Mono**.

### Typographic Rules
- **Space Grotesk** commands module headers, tactical incident identifiers, and display metrics. Its subtle technical idiosyncrasies invoke engineering terminals.
- **Inter** provides high legibility for analytical dossiers, forensic descriptions, contextual notes, and configuration copy.
- **JetBrains Mono** is enforced for any value produced by or targeted by code: IP addresses, BGP Autonomous System Numbers (ASNs), hash signatures (SHA-256), memory offsets, geolocation coordinates, and ISO 8601 UTC timestamps.
- **Micro-Labels (`label-caps`):** Must always render in uppercase with positive letter tracking (`0.08em`) to guarantee quick peripheral scanning against dark backgrounds.

## Layout & Spacing

The system implements a rigid, high-density layout paradigm optimized to present mission-critical telemetry without requiring excessive vertical scrolling.

### Grid Architecture & Form Factors
- **Desktop & Multi-Screen SOC Displays (≥ 1440px):** 12-column or 24-column modular fluid grid with `0.75rem` (12px) gutters. Outer canvas margin locked to `1rem` (16px). Paneling supports docked toolbars, split-pane packet inspectors, and persistent kill-chain status ribbons.
- **Field & Tactical Laptops (768px - 1439px):** 8-column layout. Analytical inspectors collapse into slide-out drawer overlays; telemetry cards switch to dynamic 2-column stacks.
- **Tactical Mobile (≤ 767px):** Single-column stacked stream. Margin contracts to `0.75rem` (12px), gutters set to `0.5rem` (8px). Primary focus shifts to priority-ranked alert streams and quick-action isolation triggers.

### Density Model
Spacing tokens are strictly calibrated for analytical density. The baseline component padding is `space-sm` (8px) or `space-md` (12px), keeping interactive controls compact and inline with raw tabular data.

## Elevation & Depth

Visual depth is produced through a strict system of **tonal layering and razor-sharp technical borders**, avoiding heavy drop shadows that blur analytical boundaries.

### Depth Hierarchy
1. **Floor (Elevation 0 - `#05080C`):** Base canvas background, often underlaid with a subtle, non-intrusive 24px Cartesian coordinate grid line pattern (`rgba(28, 41, 53, 0.35)`).
2. **Surface Panels (Elevation 1 - `#0B1117`):** Analytical workspace cards and timeline panels, bounded by a 1px solid border of `#1C2935`.
3. **Floating Modules & Drawers (Elevation 2 - `#101820`):** Menus, contextual inspector popovers, and filter toolbars. Bounded by a 1px solid border of `#1C2935` and subtle ambient edge darkening (`box-shadow: 0 8px 24px rgba(0, 0, 0, 0.6)`).
4. **Active Intercept & Critical Focus (Elevation 3):** High-priority modules or targeted elements adopt an active cyan hairline contour (`1px solid #00E5FF`) paired with a restrained outer phosphor radiance (`box-shadow: 0 0 12px rgba(0, 229, 255, 0.15)`). High-risk alerts switch this glow to crimson (`box-shadow: 0 0 12px rgba(239, 68, 68, 0.2)`).

## Shapes

The design language mandates a sharp, precision-tooled geometry (`roundedness: 1`). Soft curves are eliminated to maintain a mechanical, military-spec command terminal feel.

### Geometric Rules
- **Panels, Modals & Data Tables:** Standardized at `rounded` (`0.25rem` / 4px).
- **Control Elements (Inputs, Buttons, Dropdowns):** Configured at `rounded` (`0.25rem` / 4px) to retain structural alignment with grid lines.
- **Corner Accents & Framing:** Certain primary telemetry panels incorporate chamfered or notched corner styling via CSS clip-paths or pseudo-element corner markers, emphasizing tactical hardware interfaces.
- **Status Indicators:** Micro-dots, signal beacons, and port status markers remain either perfectly circular (`9999px`) or crisp squares (`0px`).

## Components

### Buttons
- **Primary Action (Intercept / Execute):** Solid `#00E5FF` fill with `#05080C` bold text. On hover, background shifts to pure white with a restrained cyan glow (`0 0 10px rgba(0, 229, 255, 0.4)`).
- **Secondary Action (Inspect / Query):** Transparent fill with a 1px border of `#1C2935` and `#E2E8F0` text. Hover prompts border transition to `#00E5FF` and surface shift to `rgba(0, 229, 255, 0.05)`.
- **Destructive Action (Sever Node / Purge Session):** 1px border of `#EF4444`, text in `#EF4444`, surface transitioning to `rgba(239, 68, 68, 0.12)` on hover.

### Badges & Intelligence Chips
- Composed using `label-caps` in `JetBrains Mono`.
- Height locked at `20px` with horizontal padding of `6px`.
- High-Risk (Crimson): Background `rgba(239, 68, 68, 0.1)`, text `#EF4444`, border `1px solid rgba(239, 68, 68, 0.3)`.
- Threat Tracking (Amber): Background `rgba(245, 158, 11, 0.1)`, text `#F59E0B`, border `1px solid rgba(245, 158, 11, 0.3)`.
- Active Telemetry (Cyan): Background `rgba(0, 229, 255, 0.08)`, text `#00E5FF`, border `1px solid rgba(0, 229, 255, 0.25)`.

### Input Fields & Search Bars
- Background `#0B1117` framed by a 1px border of `#1C2935`.
- Text typed in `JetBrains Mono` (`13px`). Placeholder text in `#94A3B8` at 50% opacity.
- Focus state switches border to `#00E5FF` with an inner glow highlight.
- Search modules must support leading technical prefix slots (e.g., `src_ip:`, `asn:`, `cve:`).

### Checkboxes & Toggles
- Checkboxes: 14x14px square boxes, `#101820` fill, 1px `#1C2935` border. Checked state renders a crisp `#00E5FF` fill with a black geometric check icon.
- Toggles: 28x16px track with a 12x12px square actuator. Active state illuminates the track edge in `#00E5FF`.

### Telemetry Cards & Metric Blocks
- Structured with `#0B1117` base, 1px `#1C2935` perimeter border.
- Header bars feature uppercase technical tags on the left and live status indicators (pulsing 6px dot) on the right.
- Numeric metrics display in `Space Grotesk` (`headline-lg`), accompanied by delta percentages and sparklines colored according to risk tolerance.

### Operational Tables
- Dense 32px row heights with strict cell borders (`1px solid #1C2935`).
- Monospaced alignment for numerical values, IP addresses, and timestamps.
- Zebra striping is avoided; row separation relies on borders, with hovered rows illuminated by `rgba(0, 229, 255, 0.03)`.