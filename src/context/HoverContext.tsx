import { createContext, useContext, useState, type ReactNode } from 'react'

interface HoverContextType {
  hoveredModel: string | null
  setHoveredModel: (id: string | null) => void
}

const HoverContext = createContext<HoverContextType>({
  hoveredModel: null,
  setHoveredModel: () => {},
})

export function HoverProvider({ children }: { children: ReactNode }) {
  const [hoveredModel, setHoveredModel] = useState<string | null>(null)
  return (
    <HoverContext.Provider value={{ hoveredModel, setHoveredModel }}>
      {children}
    </HoverContext.Provider>
  )
}

export function useHover() {
  return useContext(HoverContext)
}
