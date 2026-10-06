export type EntityID = string;
export type DeviceID = string;
export type UUID = string;
export type Timestamp = string;
export type OpaqueCursor = string;
export type Title = string;
export type Presence = 'online' | 'offline' | 'unknown';
export interface UserSummary { id: EntityID; display_name: string; avatar_attachment_id: EntityID | null }
export interface UserProfile extends UserSummary { email: string }
export interface AccessSession { access_token: string; expires_at: Timestamp; user_id: EntityID; device_id: DeviceID; session_generation: number }
export type SessionContext = ({ state: 'authenticated' } & AccessSession) | { state: 'refreshing'; user_id: EntityID; device_id: DeviceID; session_generation: number; access_token: null; expires_at: null } | { state: 'logged_out'; user_id: null; device_id: null; session_generation: null; access_token: null; expires_at: null };
export interface ContactView { user: UserSummary; added_at: Timestamp; presence?: Presence }
export interface ConversationSummary { id: EntityID; type: 'direct' | 'group'; title: Title | null; unread_count: number }
export interface MemberView { user_id: EntityID; role: 'admin' | 'member' }
export interface MemberMutationResult extends MemberView { membership_version: number }
export interface ConversationDetail extends ConversationSummary { members: MemberView[]; created_at: Timestamp; membership_version: number | null }
export interface ConversationCreateResult { id: EntityID; type: 'direct' | 'group'; title: Title | null; member_ids: EntityID[]; membership_version: number | null }
export interface ConversationMutationResult { id: EntityID; type: 'group'; title: Title; membership_version: number }
export interface ReceiptProjection { kind: 'direct'; message_id: UUID; recipient_id: EntityID; status: 'delivered' | 'read'; updated_at: Timestamp }
interface MessageBase { id: UUID; event_id: UUID; conversation_id: EntityID; sender_id: EntityID; created_at: Timestamp; order_key: string; receipt: ReceiptProjection | null; client_message_id?: UUID }
export type MessageView = MessageBase & ({ type: 'text'; text: string; attachment_id?: never } | { type: 'image' | 'file'; attachment_id: EntityID; text?: never });
export type MessageSnapshot = MessageView;
export interface AttachmentView { id: EntityID; scope: 'avatar' | 'conversation'; conversation_id: EntityID | null; uploader_id: EntityID; kind: 'image' | 'file'; filename: string; content_type: string; size_bytes: number; sha256: string; state: 'pending' | 'ready'; created_at: Timestamp }
export interface UploadGrant { attachment_id: EntityID; upload_attempt_id: EntityID; upload_url: string; expires_at: Timestamp; required_headers: Record<string,string> }
export interface DownloadGrant { download_url: string; expires_at: Timestamp; content_type: string; filename: string; size_bytes: number }
export interface BootstrapConversation extends ConversationSummary { my_role: 'admin' | 'member' | null; recent_messages: MessageSnapshot[] }
export interface SyncBootstrapPage { snapshot_id: EntityID; start_cursor: OpaqueCursor; conversations: BootstrapConversation[]; next_page_token: OpaqueCursor | null; has_more: boolean }
export interface WsEnvelope<P = Record<string, unknown>> { event: string; event_id: UUID; timestamp: Timestamp; payload: P; correlation_id?: UUID; conversation_id?: EntityID; sender_id?: EntityID }
export interface SyncBatch { snapshot_boundary: OpaqueCursor; events: WsEnvelope[]; next_cursor: OpaqueCursor; has_more: boolean }
export interface Page<T> { items: T[] }
export interface ApiResult<T> { data: T; meta?: { next_cursor: OpaqueCursor | null } }
export interface RuntimeConfig { API_BASE_URL: string; WS_URL: string; SYNC_RECONCILE_SECONDS: number }
declare global { interface Window { HINE_CONFIG?: RuntimeConfig } }
