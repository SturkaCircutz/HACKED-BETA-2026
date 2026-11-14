import { useEffect, useState } from 'react'
import { api, CATEGORIES, type Geometry } from '../api'

interface Props {
  geometry: Geometry | null
  vertexCount: number
  onCancel: () => void
  onStarted: (runId: string) => void
}

export function ReportForm({ geometry, vertexCount, onCancel, onStarted }: Props) {
  const [story, setStory] = useState('')
  const [category, setCategory] = useState('')
  const [files, setFiles] = useState<File[]>([])
  const [previews, setPreviews] = useState<string[]>([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  useEffect(() => {
    const urls = files.map((f) => URL.createObjectURL(f))
    setPreviews(urls)
    return () => urls.forEach(URL.revokeObjectURL)
  }, [files])

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!geometry) return
    setBusy(true)
    setError('')
    try {
      const photo_ids = await Promise.all(files.map((f) => api.uploadPhoto(f)))
      const run = await api.startRun({ geometry, story, category: category || undefined, photo_ids })
      onStarted(run.id)
    } catch (err) {
      setError((err as Error).message)
      setBusy(false)
    }
  }

  const where = !geometry
    ? vertexCount
      ? `Drawing area: ${vertexCount} point(s). Double-click to finish.`
      : 'Click the map to drop a pin, or switch to “Area” and click around the spot.'
    : geometry.type === 'Point'
      ? `Pin at ${geometry.coordinates[1].toFixed(5)}, ${geometry.coordinates[0].toFixed(5)}`
      : `Area with ${geometry.coordinates[0].length - 1} corners`

  return (
    <form className="panel" style={{ height: '100%' }} onSubmit={submit}>
      <div className="panel-head">
        <span className="panel-label main">New report</span>
        <span className="spacer" />
        <button type="button" className="btn ghost sm" onClick={onCancel}>Cancel</button>
      </div>
      <div className="panel-body stack">
        <div>
          <div className="eyebrow">Where</div>
          <div className={geometry ? '' : 'muted'}>{where}</div>
        </div>
        <div className="field">
          <label htmlFor="story">What did you see?</label>
          <textarea id="story" className="textarea" rows={5} value={story} onChange={(e) => setStory(e.target.value)}
            placeholder="e.g. Three mattresses and a couch dumped behind the community hall since Monday." required />
        </div>
        <div className="field">
          <label htmlFor="cat">Category <span className="muted">(optional — the agent can classify it)</span></label>
          <select id="cat" className="select" value={category} onChange={(e) => setCategory(e.target.value)}>
            <option value="">Let the agent decide</option>
            {CATEGORIES.map((c) => <option key={c} value={c}>{c}</option>)}
          </select>
        </div>
        <div className="field">
          <label>Photos</label>
          <label className="dropzone">
            <input type="file" accept="image/*" capture="environment" multiple
              onChange={(e) => setFiles([...files, ...Array.from(e.target.files ?? [])])} />
            Take a photo or choose files
          </label>
          {previews.length > 0 && (
            <div className="photos">
              {previews.map((u, i) => (
                <figure key={u}>
                  <img src={u} alt={`Photo ${i + 1}`} />
                  <button type="button" className="btn sm" style={{ position: 'absolute', right: 4, top: 4, padding: '0 6px' }}
                    aria-label="Remove photo" onClick={() => setFiles(files.filter((_, j) => j !== i))}>×</button>
                </figure>
              ))}
            </div>
          )}
        </div>
        {error && <div className="error-box">{error}</div>}
      </div>
      <div className="composer">
        <span className="small muted" style={{ flex: 1, alignSelf: 'center' }}>Nothing is sent without your approval.</span>
        <button className="btn primary" disabled={!geometry || !story.trim() || busy}>
          {busy ? 'Starting…' : 'Ask the agent →'}
        </button>
      </div>
    </form>
  )
}
