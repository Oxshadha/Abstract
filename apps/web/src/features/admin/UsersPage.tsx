import { useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Search, ShieldCheck, ShieldOff, UserCheck, UserX } from "lucide-react";
import { useEffect, useId, useState } from "react";

import { fetchMe } from "@/api/me";
import { buttonSecondary, inputClass } from "@/components/dialog/Dialog";
import { ListRowSkeleton, Loading } from "@/components/feedback/Skeleton";
import { Menu } from "@/components/menu/Menu";
import { Select } from "@/components/menu/Select";
import { StatusPill } from "@/components/status/StatusPill";
import { toast } from "@/components/status/toast";

import { adminKeys, listPlans, listUsers, setUserAdmin, setUserDisabled, setUserPlan, type AdminUser } from "./api";
import { count, money, when } from "./format";

function useDebounced(value: string, ms = 250): string {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => { setDebounced(value); }, ms);
    return () => { clearTimeout(id); };
  }, [value, ms]);
  return debounced;
}

function UserRow({ user, plans, self }: { user: AdminUser; plans: { value: string; label: string }[]; self: boolean }) {
  const queryClient = useQueryClient();
  const refresh = () => queryClient.invalidateQueries({ queryKey: ["admin", "users"] });
  const done = (message: string) => async () => {
    toast(message);
    await refresh();
  };
  const plan = useMutation({ mutationFn: (p: string) => setUserPlan(user.id, p), onSuccess: done("Plan changed."), onError: (e) => { toast(e.message); } });
  const role = useMutation({ mutationFn: (admin: boolean) => setUserAdmin(user.id, admin), onSuccess: done("Role changed."), onError: (e) => { toast(e.message); } });
  const status = useMutation({ mutationFn: (off: boolean) => setUserDisabled(user.id, off), onSuccess: done("Account updated."), onError: (e) => { toast(e.message); } });
  const name = user.display_name ?? user.email ?? "Unknown";
  return (
    <li className="flex min-w-0 items-center gap-3 py-3">
      <div className="min-w-0 flex-1">
        <p className="flex min-w-0 items-center gap-2">
          <span className="truncate font-medium" title={name}>{name}</span>
          {user.platform_role === "admin" && <StatusPill status="neutral">Admin</StatusPill>}
          {user.disabled && <StatusPill status="error">Disabled</StatusPill>}
        </p>
        <p className="truncate text-xs text-text-secondary" title={user.email ?? undefined}>
          {`${user.email ?? ""} · ${count(user.papers)} papers · ${money(user.spend_month_usd)} this month · active ${when(user.last_active)}`}
        </p>
      </div>
      <Select label={`Plan for ${name}`} value={user.plan_id} options={plans} onChange={(p) => { plan.mutate(p); }} width="w-32" compact />
      <Menu
        label={`Actions for ${name}`}
        items={[
          user.platform_role === "admin"
            ? { label: "Remove admin", icon: <ShieldOff aria-hidden className="size-4" />, onSelect: () => { role.mutate(false); }, disabled: self }
            : { label: "Make admin", icon: <ShieldCheck aria-hidden className="size-4" />, onSelect: () => { role.mutate(true); } },
          user.disabled
            ? { label: "Enable account", icon: <UserCheck aria-hidden className="size-4" />, onSelect: () => { status.mutate(false); } }
            : { label: "Disable account", icon: <UserX aria-hidden className="size-4" />, onSelect: () => { status.mutate(true); }, destructive: true, disabled: self },
        ]}
      />
    </li>
  );
}

/** Admin users (spec 011 AC5): search, plan, role and account status; never content (AC2). */
export function UsersPage() {
  const searchId = useId();
  const [q, setQ] = useState("");
  const query = useDebounced(q.trim());
  const me = useQuery({ queryKey: ["me"], queryFn: fetchMe });
  const plans = useQuery({ queryKey: adminKeys.plans, queryFn: listPlans });
  const users = useInfiniteQuery({
    queryKey: adminKeys.users(query),
    queryFn: ({ pageParam }) => listUsers(query, pageParam),
    initialPageParam: null as string | null,
    getNextPageParam: (last) => last.next_cursor,
  });
  const options = (plans.data ?? []).map((p) => ({ value: p.id, label: p.name }));
  const items = users.data?.pages.flatMap((p) => p.items) ?? [];
  return (
    <div className="flex flex-col gap-3">
      <div className="relative max-w-md">
        <label htmlFor={searchId} className="sr-only">Search users by email or name</label>
        <Search aria-hidden className="absolute top-1/2 left-3 size-4 -translate-y-1/2 text-text-secondary" />
        <input id={searchId} type="search" value={q} onChange={(e) => { setQ(e.target.value); }} placeholder="Search by email or name" className={`${inputClass} pl-9`} />
      </div>
      {users.isPending ? (
        <Loading label="Loading users"><ListRowSkeleton /><ListRowSkeleton /></Loading>
      ) : users.isError ? (
        <p role="alert">{users.error.message}</p>
      ) : items.length === 0 ? (
        <p className="text-sm text-text-secondary">No users match.</p>
      ) : (
        <ul aria-label="Users" className="flex flex-col divide-y divide-border rounded-lg border border-border bg-surface px-4">
          {items.map((u) => <UserRow key={u.id} user={u} plans={options} self={u.id === me.data?.user.id} />)}
        </ul>
      )}
      {users.hasNextPage && (
        <button type="button" disabled={users.isFetchingNextPage} onClick={() => void users.fetchNextPage()} className={`${buttonSecondary} self-start`}>
          Load more
        </button>
      )}
    </div>
  );
}
