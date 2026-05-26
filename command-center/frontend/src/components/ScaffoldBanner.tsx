import { AlertTriangle } from 'lucide-react'

export function ScaffoldBanner({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-2 text-micro text-warn-text bg-warn-muted border border-warn-muted px-3 py-[7px] rounded-md mb-4">
      <AlertTriangle size={14} className="flex-shrink-0" />
      <span>{message}</span>
    </div>
  )
}
