---
name: PaperMerge
description: A monochrome Windows desktop utility for Cambridge revision packs.
colors:
  primary: '#161616'
  background: '#f5f5f7'
  surface: '#ffffff'
  secondary-text: '#595959'
  button: '#ededed'
  button-active: '#dddddd'
  button-disabled-text: '#757575'
  primary-active: '#383838'
  primary-disabled: '#d4d4d4'
  primary-disabled-text: '#626262'
  table-heading: '#eeeeee'
  selection: '#e3e3e3'
  selection-text: '#111111'
typography:
  title:
    fontFamily: Segoe UI Semibold
    fontSize: 22pt
    fontWeight: 600
  section:
    fontFamily: Segoe UI Semibold
    fontSize: 12pt
    fontWeight: 600
  body:
    fontFamily: Segoe UI
    fontSize: 11pt
    fontWeight: 400
  action:
    fontFamily: Segoe UI Semibold
    fontSize: 11pt
    fontWeight: 600
  detail:
    fontFamily: Segoe UI
    fontSize: 10pt
    fontWeight: 400
  table-heading:
    fontFamily: Segoe UI Semibold
    fontSize: 10pt
    fontWeight: 600
spacing:
  compact: 8px
  control-y: 10px
  group: 12px
  control-x: 14px
  card: 16px
  primary-x: 22px
  header-x: 24px
  body-x: 28px
components:
  button-primary:
    backgroundColor: '{colors.primary}'
    textColor: '{colors.surface}'
    typography: '{typography.action}'
    padding: 12px 22px
  button-primary-active:
    backgroundColor: '{colors.primary-active}'
  button-primary-disabled:
    backgroundColor: '{colors.primary-disabled}'
    textColor: '{colors.primary-disabled-text}'
  button-secondary:
    backgroundColor: '{colors.button}'
    textColor: '{colors.primary}'
    typography: '{typography.body}'
    padding: 10px 14px
  button-secondary-active:
    backgroundColor: '{colors.button-active}'
  button-quiet:
    backgroundColor: '{colors.button}'
    typography: '{typography.detail}'
    padding: 4px 10px
  field:
    backgroundColor: '{colors.surface}'
    textColor: '{colors.primary}'
    typography: '{typography.body}'
    padding: 8px 10px
  filter-card:
    backgroundColor: '{colors.surface}'
    padding: 16px
  results-row:
    backgroundColor: '{colors.surface}'
    typography: '{typography.detail}'
    height: 36px
---

# Design System: PaperMerge

## Overview

**Creative North Star: "A clear revision desk"**

The user's visual commitment is clean, iOS-inspired black and white. The shipped interface applies that restraint through grouped white forms, quiet gray surroundings and black actions, using Windows Tk/ttk controls and Segoe UI. It remains a desktop utility with native keyboard behavior and file dialogs.

**Key Characteristics:**

- Monochrome hierarchy with plain, readable labels.
- Compact header and grouped filters above a flexible results table.
- Persistent space for the save actions, progress and status.
- Direct state changes without decorative animation.

## Colors

The frontmatter records the actual colors from papermerge/gui.py; there are no chromatic accent roles.

### Primary

- **Ink:** text, primary actions, dropdown selection and progress fill.
- **Active ink:** pointer-active primary actions.

### Neutral

- **Quiet background:** the window and surrounding work area.
- **White surface:** the filter card, input fields and results table.
- **Secondary text:** helper copy, catalogue status and empty states.
- **Button gray:** secondary controls, with a darker active state.
- **Heading gray:** table headings.
- **Selection gray:** selected result row and progress trough; selected text stays dark.
- **Disabled grays:** muted action backgrounds and labels distinguish unavailable actions.

**The Monochrome Rule.** Preserve the user's black-and-white direction; use text and explicit selection markers to communicate state.

## Typography

Segoe UI is the body family; Segoe UI Semibold establishes emphasis. The compact product title uses the title role, Search results uses section, and primary actions use action. Helpers and table rows use detail; headings use table-heading.

Tk font sizes are points, while padding and table dimensions are pixels. Windows DPI scaling affects their rendered size. Line height and letter spacing are inherited from Tk rather than explicitly set. The internal, unmounted log widget uses Segoe UI at 9pt and is not part of the visible hierarchy.

## Layout

The window starts at 1120 × 900 and has a 900 × 760 minimum. The header has 24px horizontal and 12px vertical padding; the tagline sits beside the product title. The body has 28px side padding and 18px bottom padding. The white filter card has 16px internal padding.

The first filter row holds qualification, subject collection and a wider subject field. Catalogue status and Refresh subjects sit below it. The next row holds From year, To year, Exam session and Include. A third row contains Paper / variant and its helper text. Common field gaps are 12px; labels sit 5px above fields. The subject column and filter groups expand horizontally.

Inline validation precedes Find papers, Cancel and the result count. The separate Search results field and Clear search button sit immediately above the table. The table expands with the window and scrolls vertically. Its visible columns are Use, Paper file, Year, Session, Document and Variant; source data is retained but the Source column is hidden. The filename column stretches.

The bottom region reserves its space before the results table expands. Select all papers and Select none sit on the left; Open saved PDF sits beside Save merged PDF on the right. Progress and status appear below. There is no visible footer or log panel. This is a desktop layout with a minimum size, not a mobile breakpoint system.

## Elevation & Depth

The implementation defines no custom shadows. White surfaces, the quiet window background and table-heading gray provide grouping. Tk's clam theme supplies the remaining control borders, arrows and focus treatment. The progress bar uses a thin 5px treatment.

## Shapes

Controls and containers use the squared geometry of the clam theme. No custom rounded-corner tokens or clipping are implemented. Button and table border widths are explicitly zero where configured; field outlines and other platform details remain theme-owned.

## Components

### Buttons

Primary black buttons mark Find papers and Save merged PDF. Secondary gray buttons support cancellation, selection, search clearing and opening the saved file. Refresh subjects uses the compact quiet variant. Pointer-active and disabled colors are recorded in the frontmatter; focus behavior remains Tk-native.

### Fields and dropdowns

White fields share padded interiors. Qualification, subject collection, session and document type are readonly dropdowns. Subject matches name or syllabus code as the value changes. From year, To year and Paper / variant filter choices on typing or dropdown opening. Exact variants remain valid text input. General dropdowns show up to twelve choices, and the subject dropdown up to fifteen. Dropdown arrows use a 16px size.

### Results table

Rows are 36px high, with explicit [x] / [ ] inclusion markers. Clicking any row cell or pressing Space toggles inclusion. Gray row selection identifies the focused browsing row and remains distinct from inclusion. Search hides unmatched rows without losing their inclusion state; Select all papers and Select none apply to the entire loaded result set.

### Feedback

Empty-state text sits centered within the white results area and states the next step. Validation appears above the Find row. While network work runs, relevant filter controls and actions disable, Cancel becomes available, and progress/status communicate activity. Successful save enables Open saved PDF and shows the native success dialog. Error dialogs and inline status retain the same plain-language hierarchy.

## Do's and Don'ts

### Do:

- **Do** preserve the compact 22pt title and reserved bottom action region.
- **Do** keep searchable dropdowns, visible labels and exact-variant guidance together.
- **Do** retain readable monochrome selection, disabled and empty states.
- **Do** preserve Windows keyboard behavior and native file dialogs.

### Don't:

- **Don't** introduce colored accents or a phone-shaped app shell.
- **Don't** replace actual Tk geometry with invented rounded cards or shadows.
- **Don't** let an expanding results table push Save, Open, progress or status out of view.
- **Don't** describe the curated Top 20 collections as official or verified popularity rankings.

