import { useEffect, useRef } from 'react'
import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
// Bundle MapLibre's web worker with Vite; its default relative URL breaks after dep pre-bundling.
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import type { Geometry, Report } from '../api'

export type PickMode = 'browse' | 'point' | 'polygon'
export type BBox = [number, number, number, number]

maplibregl.setWorkerUrl(workerUrl)

const OSM_STYLE: maplibregl.StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: 'raster',
      tiles: ['https://tile.openstreetmap.org/{z}/{x}/{y}.png'],
      tileSize: 256,
      maxzoom: 19,
      attribution: '© OpenStreetMap contributors',
    },
  },
  layers: [{ id: 'osm', type: 'raster', source: 'osm' }],
}
const STATUS_COLOR = ['match', ['get', 'status'],
  'open', '#e5484d', 'action_sent', '#f08c2e', 'acknowledged', '#e2b714', 'resolved', '#30a46c', '#9aa1b0']
const EMPTY = { type: 'FeatureCollection' as const, features: [] }

interface Props {
  reports: Report[]
  mode: PickMode
  draft: Geometry | null
  draftVertices: [number, number][]
  selectedId: string | null
  flyTo: { lng: number; lat: number; zoom?: number; seq: number } | null
  onBounds: (bbox: BBox) => void
  onSelect: (id: string) => void
  onPoint: (lngLat: [number, number]) => void
  onVertex: (lngLat: [number, number]) => void
  onFinishPolygon: () => void
}

export function MapView(props: Props) {
  const el = useRef<HTMLDivElement>(null)
  const map = useRef<maplibregl.Map | null>(null)
  const latest = useRef(props)
  latest.current = props

  useEffect(() => {
    const styleUrl = import.meta.env.VITE_MAP_STYLE_URL
    const m = new maplibregl.Map({
      container: el.current!,
      style: styleUrl || OSM_STYLE,
      center: [-113.4938, 53.5461], // Edmonton
      zoom: 12,
      doubleClickZoom: false,
    })
    map.current = m
    m.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    m.addControl(new maplibregl.GeolocateControl({ trackUserLocation: false }), 'top-right')

    const emitBounds = () => {
      const b = m.getBounds()
      latest.current.onBounds([b.getWest(), b.getSouth(), b.getEast(), b.getNorth()])
    }

    m.on('load', () => {
      m.addSource('reports', { type: 'geojson', data: EMPTY })
      m.addSource('draft', { type: 'geojson', data: EMPTY })
      m.addLayer({ id: 'report-areas', type: 'fill', source: 'reports', filter: ['==', ['geometry-type'], 'Polygon'],
        paint: { 'fill-color': STATUS_COLOR as never, 'fill-opacity': 0.18 } })
      m.addLayer({ id: 'report-pins', type: 'circle', source: 'reports', filter: ['==', ['get', 'kind'], 'pin'],
        paint: {
          'circle-color': STATUS_COLOR as never,
          'circle-radius': ['case', ['get', 'selected'], 10, 7],
          'circle-stroke-color': '#fff',
          'circle-stroke-width': ['case', ['get', 'selected'], 3, 2],
        } })
      m.addLayer({ id: 'draft-fill', type: 'fill', source: 'draft', filter: ['==', ['geometry-type'], 'Polygon'],
        paint: { 'fill-color': '#2f5bd3', 'fill-opacity': 0.15 } })
      m.addLayer({ id: 'draft-line', type: 'line', source: 'draft', filter: ['!=', ['geometry-type'], 'Point'],
        paint: { 'line-color': '#2f5bd3', 'line-width': 2, 'line-dasharray': [2, 1] } })
      m.addLayer({ id: 'draft-pts', type: 'circle', source: 'draft', filter: ['==', ['geometry-type'], 'Point'],
        paint: { 'circle-color': '#2f5bd3', 'circle-radius': 6, 'circle-stroke-color': '#fff', 'circle-stroke-width': 2 } })
      emitBounds()
      syncReports()
      syncDraft()
    })
    m.on('moveend', emitBounds)
    m.on('click', 'report-pins', (e) => {
      if (latest.current.mode !== 'browse') return
      const id = e.features?.[0]?.properties?.id
      if (id) latest.current.onSelect(String(id))
    })
    m.on('mouseenter', 'report-pins', () => { if (latest.current.mode === 'browse') m.getCanvas().style.cursor = 'pointer' })
    m.on('mouseleave', 'report-pins', () => { m.getCanvas().style.cursor = '' })
    m.on('click', (e) => {
      const p = latest.current
      const ll: [number, number] = [e.lngLat.lng, e.lngLat.lat]
      if (p.mode === 'point') p.onPoint(ll)
      else if (p.mode === 'polygon') p.onVertex(ll)
    })
    m.on('dblclick', () => { if (latest.current.mode === 'polygon') latest.current.onFinishPolygon() })
    return () => m.remove()
  }, [])

  function syncReports() {
    const src = map.current?.getSource('reports') as maplibregl.GeoJSONSource | undefined
    if (!src) return
    const { reports, selectedId } = latest.current
    src.setData({
      type: 'FeatureCollection',
      features: reports.flatMap((r) => {
        const props = { id: r.id, status: r.status, selected: r.id === selectedId }
        const pin = { type: 'Feature' as const, properties: { ...props, kind: 'pin' },
          geometry: { type: 'Point' as const, coordinates: [r.lng, r.lat] } }
        return r.geometry.type === 'Polygon'
          ? [{ type: 'Feature' as const, properties: { ...props, kind: 'area' }, geometry: r.geometry }, pin]
          : [pin]
      }),
    })
  }

  function syncDraft() {
    const src = map.current?.getSource('draft') as maplibregl.GeoJSONSource | undefined
    if (!src) return
    const { draft, draftVertices } = latest.current
    const features: { type: "Feature"; properties: object; geometry: Geometry | { type: "Point"; coordinates: [number, number] } | { type: "LineString"; coordinates: [number, number][] } }[] = []
    if (draft) features.push({ type: 'Feature', properties: {}, geometry: draft })
    if (!draft && draftVertices.length) {
      draftVertices.forEach((v) => features.push({ type: 'Feature', properties: {}, geometry: { type: 'Point', coordinates: v } }))
      if (draftVertices.length > 1)
        features.push({ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: draftVertices } })
    }
    src.setData({ type: 'FeatureCollection', features })
  }

  useEffect(syncReports, [props.reports, props.selectedId])
  useEffect(syncDraft, [props.draft, props.draftVertices])
  useEffect(() => {
    const c = map.current?.getCanvas()
    if (c) c.style.cursor = props.mode === 'browse' ? '' : 'crosshair'
  }, [props.mode])
  useEffect(() => {
    if (props.flyTo) map.current?.flyTo({ center: [props.flyTo.lng, props.flyTo.lat], zoom: props.flyTo.zoom ?? 16 })
  }, [props.flyTo])

  return <div ref={el} className="map" role="application" aria-label="Map. Click to place a pin." />
}
