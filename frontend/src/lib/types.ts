export type FilterCard = {
  id: string;
  name?: string | null;
  name_en?: string | null;
  rarity?: string | null;
  colors?: string[];
  cost?: number | null;
  power?: number | null;
  counter?: number | null;
  card_type?: string | null;
  block_number?: number | null;
  attributes?: string[];
  img_url?: string | null;
  img_full_url?: string | null;
  img_local_url?: string | null;
};

export type Card = {
  id: string;
  name?: string | null;
  name_en?: string | null;
  rarity?: string | null;
  colors?: string[];
  colors_en?: string[];
  pack_id?: string | null;
  img_local_url?: string | null;
  img_url?: string | null;
  img_full_url?: string | null;
  alt_image_urls?: string[];
  cost?: number | null;
  effect?: string | null;
  effect_en?: string | null;
  trigger?: string | null;
  trigger_en?: string | null;
  power?: number | string | null;
  traits?: string[];
  traits_en?: string[];
  card_type?: string | null;
  card_type_en?: string | null;
  counter?: number | string | null;
  block_number?: number | null;
  attributes?: string[];
  attributes_en?: string[];
  card_sets?: string[];
  /** base + parallel id → official getInfo for the active illustration */
  variant_card_sets?: Record<string, string[]>;
  market_price?: Record<string, unknown> | null;
  life?: number | null;
};

export type CardDetailResponse = {
  card: Card;
  ai_advice?: Record<string, unknown> | null;
  ai_error?: string | null;
  meta_evidence?: Record<string, unknown> | null;
};

export type PriceHistoryPoint = {
  ts: string;
  price: number | null;
};

export type CardPriceResponse = {
  card_id: string;
  source: string;
  currency: string;
  current_price: number | null;
  last_seen?: string | null;
  last_checked?: string | null;
  history: PriceHistoryPoint[];
  message?: string;
};

export type FilterOptions = {
  series: string[];
  rarities: string[];
  blocks: number[];
  keywords?: string[];
};

export type LoginResponse = {
  token: string;
  username: string;
  email: string;
  email_verified: boolean;
};

export type MeResponse = {
  username: string;
  email: string;
  email_verified: boolean;
  is_admin?: boolean;
};

export type CommunityCategory = {
  id: number;
  slug: string;
  title_zh_hant: string;
  title_zh_hans: string;
  title_en: string;
  sort: number;
  active: number;
};

export type CommunityTag = {
  id: number;
  slug: string;
  title_zh_hant: string;
  title_zh_hans: string;
  title_en: string;
};

export type CommunityAuthorFields = {
  anonymous: boolean;
  author_display: string;
  author_user_id?: string | null;
  username?: string | null;
  is_self?: boolean;
  is_author_admin?: boolean;
};

export type CommunityThreadListResult = {
  threads: CommunityThread[];
  total: number;
  has_more: boolean;
  offset: number;
  limit: number;
};

export type CommunityThread = CommunityAuthorFields & {
  id: number;
  category_id: number;
  title: string;
  body?: string;
  excerpt?: string;
  category_slug?: string;
  category_title_zh_hant?: string;
  category_title_zh_hans?: string;
  category_title_en?: string;
  pinned: boolean;
  locked: boolean;
  deleted?: boolean;
  created_at: string;
  updated_at: string;
  edited_at?: string | null;
  reply_count: number;
  like_count: number;
  liked_by_me: boolean;
  tags: CommunityTag[];
};

export type CommunityPost = CommunityAuthorFields & {
  id: number;
  thread_id: number;
  parent_post_id: number | null;
  body: string;
  deleted?: boolean;
  created_at: string;
  edited_at?: string | null;
  like_count: number;
  liked_by_me: boolean;
  thread_title?: string;
  replies?: CommunityPost[];
};

export type CommunityReport = {
  id: number;
  reporter_user_id: string;
  reporter_username?: string | null;
  target_type: string;
  target_id: number;
  reason: string;
  status: string;
  created_at: string;
  target_author_user_id?: string;
  target_author_username?: string | null;
  target_preview?: string;
  thread_id?: number;
};

export type CollectionResponse = {
  owner: string;
  cards: Record<string, number>;
  total_unique: number;
  total_copies: number;
};

export type Deck = {
  id: string;
  name: string;
  leader_card_id?: string | null;
  cards: Record<string, number>;
  non_leader_count: number;
  total_count: number;
  is_valid_ready: boolean;
  created_at: string;
  updated_at: string;
};

export type DeckListResponse = {
  user_id: string;
  decks: Deck[];
};

export type BinderResponse = {
  owner: string;
  pages: (string | null)[][];
  page_titles: string[];
};

export type BinderShareCreateResponse = {
  token: string;
  url_path: string;
  owner_name: string;
};

export type BinderSharedResponse = {
  token: string;
  owner_name: string;
  pages: (string | null)[][];
  page_titles: string[];
};

export type PhotoRecognizeResponse = {
  card_id?: string | null;
  base_card_id?: string | null;
  distance?: number | null;
  confidence?: string;
  message?: string;
  candidates?: Array<Record<string, unknown>>;
  score_gap?: number | null;
  stage?: string;
  debug?: Record<string, unknown>;
};

export type FilterState = {
  colors: string[];
  costs: string[];
  counters: string[];
  powers: string[];
  card_types: string[];
  attributes: string[];
  keywords: string[];
  serieses: string[];
  rarities: string[];
  blocks: string[];
};
