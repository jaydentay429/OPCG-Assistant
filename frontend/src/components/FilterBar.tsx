"use client";

import type { FilterOptions, FilterState } from "@/lib/types";
import { useI18n } from "@/lib/i18n";
import {
  FILTER_KEYWORD_IDS,
  filterGroupValueKind,
  localizeFilterToken,
} from "@/lib/filterLabels";
import { useEffect, useRef, useState } from "react";

const COLORS = ["Red", "Blue", "Green", "Purple", "Black", "Yellow"];
const TYPES = ["Leader", "Character", "Event", "Stage", "Don"];
const COSTS = ["0", "1", "2", "3", "4", "5", "6", "7", "8", "9", "10"];
const COUNTERS = ["0", "1000", "2000"];
const POWERS = ["0", "1000", "2000", "3000", "4000", "5000", "6000", "7000", "8000", "9000", "10000"];
const ATTRS = ["Strike", "Slash", "Special", "Ranged", "Wisdom"];

type FilterKey = keyof FilterState;

type Props = {
  options: FilterOptions | null;
  value: FilterState;
  onChange: (next: FilterState) => void;
};

type FilterGroup = {
  key: FilterKey;
  label: string;
  items: string[];
};

function MultiPop({
  groupKey,
  label,
  items,
  selected,
  isOpen,
  onOpenChange,
  onToggle,
  displayItem,
}: {
  groupKey: FilterKey;
  label: string;
  items: string[];
  selected: string[];
  isOpen: boolean;
  onOpenChange: (groupKey: FilterKey, isOpen: boolean) => void;
  onToggle: (v: string) => void;
  displayItem: (v: string) => string;
}) {
  return (
    <details className="filter-pop" open={isOpen}>
      <summary
        className="filter-summary"
        onClick={(e) => {
          e.preventDefault();
          onOpenChange(groupKey, !isOpen);
        }}
      >
        <span className="filter-summary-label">
          {label}
          {selected.length ? ` (${selected.length})` : ""}
        </span>
      </summary>
      <div className="filter-panel">
        {items.map((item) => (
          <label key={item}>
            <input type="checkbox" checked={selected.includes(item)} onChange={() => onToggle(item)} />
            <span className="filter-item-text">{displayItem(item)}</span>
          </label>
        ))}
      </div>
    </details>
  );
}

function toggleIn(list: string[], v: string): string[] {
  return list.includes(v) ? list.filter((x) => x !== v) : [...list, v];
}

export function FilterBar({ options, value, onChange }: Props) {
  const { t, lang } = useI18n();
  const [openKey, setOpenKey] = useState<FilterKey | null>(null);
  const filterBarRef = useRef<HTMLDivElement | null>(null);
  const set = (patch: Partial<FilterState>) => onChange({ ...value, ...patch });

  useEffect(() => {
    if (!openKey) return;
    const onPointerDown = (e: PointerEvent) => {
      const root = filterBarRef.current;
      if (!root) return;
      if (e.target instanceof Node && root.contains(e.target)) return;
      setOpenKey(null);
    };
    document.addEventListener("pointerdown", onPointerDown);
    return () => document.removeEventListener("pointerdown", onPointerDown);
  }, [openKey]);

  const keywordItems =
    options?.keywords?.length ? options.keywords : [...FILTER_KEYWORD_IDS];

  const groups: FilterGroup[] = [
    { key: "serieses", label: t("filter.series"), items: options?.series || [] },
    { key: "colors", label: t("filter.color"), items: COLORS },
    { key: "card_types", label: t("filter.type"), items: TYPES },
    { key: "costs", label: t("filter.cost"), items: COSTS },
    { key: "powers", label: t("filter.power"), items: POWERS },
    { key: "counters", label: t("filter.counter"), items: COUNTERS },
    { key: "rarities", label: t("filter.rarity"), items: options?.rarities || [] },
    { key: "attributes", label: t("filter.attr"), items: ATTRS },
    { key: "keywords", label: t("filter.effect"), items: keywordItems },
    { key: "blocks", label: t("filter.block"), items: (options?.blocks || []).map(String) },
  ];

  const labelValue = (groupKey: FilterKey, item: string) =>
    localizeFilterToken(filterGroupValueKind(groupKey), item, lang);

  const chips = groups.flatMap((group) =>
    (value[group.key] || []).map((item) => ({
      groupKey: group.key,
      label:
        group.key === "keywords"
          ? labelValue(group.key, item)
          : `${group.label}: ${labelValue(group.key, item)}`,
      value: item,
    })),
  );

  return (
    <div className="filter-wrap">
      <div className="filter-head-row">
        <span className="muted">{t("filter.active", { count: chips.length })}</span>
        <button
          type="button"
          className="ghost filter-clear-btn"
          disabled={chips.length === 0}
          onClick={() => onChange(EMPTY_FILTERS)}
        >
          {t("filter.clear")}
        </button>
      </div>

      {chips.length > 0 ? (
        <div className="filter-chip-row">
          {chips.map((chip) => (
            <button
              key={`${chip.groupKey}-${chip.value}`}
              type="button"
              className="filter-chip"
              onClick={() =>
                set({
                  [chip.groupKey]: value[chip.groupKey].filter((x) => x !== chip.value),
                })
              }
              title={t("filter.remove")}
            >
              {chip.label} ×
            </button>
          ))}
        </div>
      ) : null}

      <div className="filter-bar" ref={filterBarRef}>
        {groups.map((group) => (
          <MultiPop
            key={group.key}
            groupKey={group.key}
            label={group.label}
            items={group.items}
            selected={value[group.key] || []}
            isOpen={openKey === group.key}
            displayItem={(item) => labelValue(group.key, item)}
            onOpenChange={(groupKey, isOpen) =>
              setOpenKey((prev) => {
                if (isOpen) return groupKey;
                return prev === groupKey ? null : prev;
              })
            }
            onToggle={(v) =>
              set({
                [group.key]: toggleIn(value[group.key] || [], v),
              })
            }
          />
        ))}
      </div>
    </div>
  );
}

export const EMPTY_FILTERS: FilterState = {
  colors: [],
  costs: [],
  counters: [],
  powers: [],
  card_types: [],
  attributes: [],
  keywords: [],
  serieses: [],
  rarities: [],
  blocks: [],
};
