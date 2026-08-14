import { useState } from 'react'
import { Trash2 } from 'lucide-react'
import { useUsers, useAddUser, useRemoveUser, useUpdateUserRole } from '@/hooks/useBots'
import type { TelegramUser } from '@/types'

const ROLES = ['admin', 'readonly'] as const

function RoleBadge({ role }: { role: string }) {
  const isAdmin = role === 'admin'
  return (
    <span
      className={`inline-flex text-[10px] font-semibold px-2 py-[3px] rounded-pill uppercase tracking-[0.4px] ${
        isAdmin ? 'bg-accent-muted text-accent' : 'bg-bg-surface-2 text-text-secondary'
      }`}
    >
      {role}
    </span>
  )
}

function UserRow({
  user,
  onRemove,
  onRoleChange,
  isBusy,
  isActing,
}: {
  user: TelegramUser
  onRemove: () => void
  onRoleChange: (role: string) => void
  /** A write is in flight somewhere — every row is locked, see the note in UsersTab. */
  isBusy: boolean
  /** …and it is THIS row's. Only one row can say so, which is what makes the lock read as
   *  "waiting for that one" rather than "the page broke". */
  isActing: boolean
}) {
  const [confirmRemove, setConfirmRemove] = useState(false)

  return (
    <tr
      className={`border-b border-border-subtle transition-colors duration-[80ms] ${
        isActing ? 'bg-accent-muted/30' : 'hover:bg-bg-hover/40'
      }`}
    >
      <td className="px-6 py-[11px] font-medium text-small align-middle">{user.name}</td>
      <td className="px-6 py-[11px] font-mono text-[11px] text-text-secondary align-middle">
        {user.chat_id}
      </td>
      <td className="px-6 py-[11px] align-middle">
        <select
          value={user.role}
          onChange={(e) => onRoleChange(e.target.value)}
          disabled={isBusy}
          className="text-[11px] bg-bg-surface border border-border-subtle rounded px-2 py-[4px] text-text-primary focus:outline-none focus:border-accent disabled:opacity-40 cursor-pointer"
        >
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
      </td>
      <td className="px-6 py-[11px] text-small text-text-tertiary align-middle">{user.added}</td>
      <td className="px-6 py-[11px] align-middle">
        {isActing ? (
          <span className="text-[11px] text-text-tertiary">Saving…</span>
        ) : confirmRemove ? (
          <div className="flex items-center gap-2">
            <span className="text-[11px] text-neg-text">Remove?</span>
            <button
              onClick={() => {
                onRemove()
                setConfirmRemove(false)
              }}
              disabled={isBusy}
              className="text-[11px] px-2 py-[3px] rounded bg-neg-muted text-neg-text border border-neg/40 hover:bg-neg/10 transition-colors disabled:opacity-40"
            >
              Yes
            </button>
            <button
              onClick={() => setConfirmRemove(false)}
              className="text-[11px] px-2 py-[3px] rounded border border-border-default bg-bg-surface text-text-secondary hover:bg-bg-hover transition-colors"
            >
              Cancel
            </button>
          </div>
        ) : (
          <button
            title="Remove user"
            onClick={() => setConfirmRemove(true)}
            disabled={isBusy}
            className="flex items-center justify-center w-[26px] h-[26px] rounded-md border border-border-subtle text-text-secondary hover:text-neg-text hover:bg-neg-muted hover:border-neg/40 transition-colors duration-[100ms] disabled:opacity-25 disabled:cursor-not-allowed"
          >
            <Trash2 size={12} />
          </button>
        )}
      </td>
    </tr>
  )
}

export function UsersTab() {
  const { data: users, isLoading, error } = useUsers()
  const addUser = useAddUser()
  const removeUser = useRemoveUser()
  const updateRole = useUpdateUserRole()

  const [form, setForm] = useState({ chatId: '', name: '', role: 'readonly' })
  const [formError, setFormError] = useState<string | null>(null)

  function handleAdd() {
    if (!form.chatId.trim() || !form.name.trim()) {
      setFormError('Chat ID and name are required.')
      return
    }
    setFormError(null)
    addUser.mutate(
      { chat_id: form.chatId.trim(), name: form.name.trim(), role: form.role },
      { onSuccess: () => setForm({ chatId: '', name: '', role: 'readonly' }) }
    )
  }

  // ── Why every row locks while one is saving ────────────────────────────────
  // Each of these endpoints rewrites the WHOLE users.json, so two in flight at once means
  // the second one's read can predate the first one's write and silently undo it. The
  // backend holds a lock across its own read-modify-write (`routers/bots._USERS_LOCK`), so
  // this is not the only thing standing between us and a lost update — but serialising here
  // too means the page never shows a change that is about to be overwritten.
  //
  // What changed on 2026-08-04 is legibility, not the locking: the acting row now says
  // `Saving…` and tints, so a table of greyed-out controls reads as "waiting for that one"
  // instead of "everything broke".
  const anyMutating = addUser.isPending || removeUser.isPending || updateRole.isPending
  const actingChatId =
    (removeUser.isPending ? removeUser.variables : undefined) ??
    (updateRole.isPending ? updateRole.variables?.chatId : undefined)

  return (
    <div>
      <div className="mb-4">
        <h2 className="text-[13px] font-semibold mb-[4px]">Telegram Users</h2>
        <p className="text-[11px] text-text-tertiary">
          Users authorised to interact with the Telegram bot. Changes are written directly to{' '}
          <span className="font-mono">users.json</span> on the VPS and take effect immediately.
        </p>
      </div>

      {isLoading && (
        <div className="text-small text-text-tertiary py-6 text-center">
          Loading users from VPS…
        </div>
      )}
      {error && (
        <div className="text-small text-neg-text bg-neg-muted border border-neg-muted rounded-md px-4 py-3 mb-4">
          Failed to load users: {String(error)}
        </div>
      )}

      {users && (
        <div className="bg-bg-surface border border-border-subtle rounded-lg overflow-hidden mb-5">
          <table className="w-full border-collapse">
            <thead>
              <tr>
                {['Name', 'Chat ID', 'Role', 'Added', ''].map((h) => (
                  <th
                    key={h}
                    className="text-left text-[10px] font-semibold uppercase tracking-[0.7px] text-text-tertiary px-6 py-[10px] bg-bg-surface-2 border-b border-border-subtle whitespace-nowrap align-middle"
                  >
                    {h}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {users.length === 0 && (
                <tr>
                  <td colSpan={5} className="text-center py-8 text-small text-text-tertiary">
                    No users configured. Add one below.
                  </td>
                </tr>
              )}
              {users.map((u) => (
                <UserRow
                  key={u.chat_id}
                  user={u}
                  isBusy={anyMutating}
                  isActing={actingChatId === u.chat_id}
                  onRemove={() => removeUser.mutate(u.chat_id)}
                  onRoleChange={(role) => updateRole.mutate({ chatId: u.chat_id, role })}
                />
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* ── Add user form ─────────────────────────────────────────────────────── */}
      <div className="bg-bg-surface border border-border-subtle rounded-lg p-4">
        <div className="text-[12px] font-semibold mb-3 text-text-secondary uppercase tracking-[0.5px]">
          Add user
        </div>
        <div className="flex items-start gap-2 flex-wrap">
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-text-tertiary uppercase tracking-[0.5px]">
              Chat ID
            </label>
            <input
              type="text"
              placeholder="429207285"
              value={form.chatId}
              onChange={(e) => setForm((f) => ({ ...f, chatId: e.target.value }))}
              className="text-[12px] bg-bg-sunken border border-border-subtle rounded px-3 py-[6px] text-text-primary placeholder-text-tertiary focus:outline-none focus:border-accent w-36 font-mono"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-text-tertiary uppercase tracking-[0.5px]">
              Name
            </label>
            <input
              type="text"
              placeholder="Aaron"
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              className="text-[12px] bg-bg-sunken border border-border-subtle rounded px-3 py-[6px] text-text-primary placeholder-text-tertiary focus:outline-none focus:border-accent w-36"
            />
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-text-tertiary uppercase tracking-[0.5px]">
              Role
            </label>
            <select
              value={form.role}
              onChange={(e) => setForm((f) => ({ ...f, role: e.target.value }))}
              className="text-[12px] bg-bg-sunken border border-border-subtle rounded px-3 py-[6px] text-text-primary focus:outline-none focus:border-accent cursor-pointer"
            >
              {ROLES.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </div>
          <div className="flex flex-col gap-1">
            <label className="text-[10px] text-transparent uppercase tracking-[0.5px]">_</label>
            <button
              onClick={handleAdd}
              disabled={anyMutating}
              className="text-[12px] px-4 py-[6px] rounded-md bg-accent-muted text-accent border border-accent/30 hover:bg-accent/10 transition-colors font-medium disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {addUser.isPending ? 'Adding…' : 'Add user'}
            </button>
          </div>
        </div>
        {formError && <p className="text-[11px] text-neg-text mt-2">{formError}</p>}
        <p className="text-[10px] text-text-tertiary mt-3">
          Tip: ask users to message <span className="font-mono">@userinfobot</span> on Telegram to
          get their chat ID.
        </p>
      </div>

      {/* ── Role legend ──────────────────────────────────────────────────────── */}
      <div className="mt-4 flex gap-4 text-[11px] text-text-tertiary">
        <div className="flex items-center gap-[6px]">
          <RoleBadge role="admin" />
          <span>Full control — all commands including stop/start</span>
        </div>
        <div className="flex items-center gap-[6px]">
          <RoleBadge role="readonly" />
          <span>Read-only — status, balance, trades</span>
        </div>
      </div>
    </div>
  )
}
