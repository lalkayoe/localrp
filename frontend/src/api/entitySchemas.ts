/**
 * Declarative field schema for each non-character memory entity type.
 * The Memory Editor renders forms straight off these definitions instead
 * of needing a bespoke component per entity type.
 */
export type FieldKind = "text" | "textarea" | "number" | "boolean" | "tags";

export interface FieldDef {
  key: string;
  label: string;
  kind: FieldKind;
  placeholder?: string;
}

export interface EntitySchema {
  type: string;
  labelRu: string;
  fields: FieldDef[];
}

export const ENTITY_SCHEMAS: Record<string, EntitySchema> = {
  location: {
    type: "location",
    labelRu: "Локации",
    fields: [
      { key: "name", label: "Название", kind: "text" },
      { key: "description", label: "Описание", kind: "textarea" },
    ],
  },
  item: {
    type: "item",
    labelRu: "Предметы",
    fields: [
      { key: "name", label: "Название", kind: "text" },
      { key: "description", label: "Описание", kind: "textarea" },
    ],
  },
  organization: {
    type: "organization",
    labelRu: "Организации",
    fields: [
      { key: "name", label: "Название", kind: "text" },
      { key: "description", label: "Описание", kind: "textarea" },
    ],
  },
  event: {
    type: "event",
    labelRu: "События",
    fields: [
      { key: "title", label: "Заголовок", kind: "text" },
      { key: "description", label: "Описание", kind: "textarea" },
      { key: "story_day", label: "День истории", kind: "number" },
    ],
  },
  fact: {
    type: "fact",
    labelRu: "Факты",
    fields: [{ key: "content", label: "Содержание", kind: "textarea" }],
  },
  goal: {
    type: "goal",
    labelRu: "Цели",
    fields: [
      { key: "description", label: "Описание", kind: "textarea" },
      { key: "is_completed", label: "Достигнута", kind: "boolean" },
    ],
  },
  promise: {
    type: "promise",
    labelRu: "Обещания",
    fields: [
      { key: "description", label: "Описание", kind: "textarea" },
      { key: "is_fulfilled", label: "Выполнено", kind: "boolean" },
      { key: "is_broken", label: "Нарушено", kind: "boolean" },
    ],
  },
  secret: {
    type: "secret",
    labelRu: "Секреты",
    fields: [{ key: "description", label: "Описание", kind: "textarea" }],
  },
  relationship: {
    type: "relationship",
    labelRu: "Отношения",
    fields: [
      { key: "label", label: "Тип отношений", kind: "text", placeholder: "друзья, соперники..." },
      { key: "description", label: "Описание", kind: "textarea" },
      { key: "intensity", label: "Интенсивность (1-10)", kind: "number" },
    ],
  },
  story_arc: {
    type: "story_arc",
    labelRu: "Сюжетные линии",
    fields: [
      { key: "title", label: "Заголовок", kind: "text" },
      { key: "description", label: "Описание", kind: "textarea" },
      { key: "is_resolved", label: "Завершена", kind: "boolean" },
    ],
  },
  scene_summary: {
    type: "scene_summary",
    labelRu: "Сцены (summary)",
    fields: [
      { key: "summary", label: "Краткое содержание", kind: "textarea" },
      { key: "story_day", label: "День истории", kind: "number" },
    ],
  },
  arc_summary: {
    type: "arc_summary",
    labelRu: "Арки (summary)",
    fields: [{ key: "summary", label: "Краткое содержание", kind: "textarea" }],
  },
};

export const ENTITY_TYPE_ORDER = [
  "character",
  "location",
  "item",
  "organization",
  "event",
  "fact",
  "goal",
  "promise",
  "secret",
  "relationship",
  "story_arc",
  "scene_summary",
  "arc_summary",
];

export const ENTITY_TYPE_LABELS_RU: Record<string, string> = {
  character: "Персонажи",
  ...Object.fromEntries(Object.values(ENTITY_SCHEMAS).map((s) => [s.type, s.labelRu])),
};
