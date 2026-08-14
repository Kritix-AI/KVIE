import React, { useEffect, useRef } from 'react'
import './AnimatedBackground.css'

const AnimatedBackground: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let animationId: number
    let waveOffset = 0

    const resize = () => {
      canvas.width = window.innerWidth
      canvas.height = window.innerHeight
    }

    const draw = () => {
      const width = canvas.width
      const height = canvas.height

      // Clear canvas
      ctx.fillStyle = '#0a0a1a'
      ctx.fillRect(0, 0, width, height)

      // Draw gradient overlay
      const gradient = ctx.createRadialGradient(width / 2, height / 2, 0, width / 2, height / 2, width)
      gradient.addColorStop(0, 'rgba(139, 92, 246, 0.15)')
      gradient.addColorStop(0.5, 'rgba(236, 72, 153, 0.1)')
      gradient.addColorStop(1, 'rgba(6, 182, 212, 0.05)')
      ctx.fillStyle = gradient
      ctx.fillRect(0, 0, width, height)

      // Draw animated waves
      waveOffset += 0.02

      for (let i = 0; i < 3; i++) {
        ctx.beginPath()
        ctx.moveTo(0, height * 0.6 + i * 50)

        for (let x = 0; x <= width; x += 10) {
          const y = height * 0.5 + i * 30 + Math.sin(x * 0.005 + waveOffset + i) * 50
          ctx.lineTo(x, y)
        }

        ctx.lineTo(width, height)
        ctx.lineTo(0, height)
        ctx.closePath()

        const waveGradient = ctx.createLinearGradient(0, 0, width, height)
        waveGradient.addColorStop(0, `rgba(139, 92, 246, ${0.1 - i * 0.02})`)
        waveGradient.addColorStop(1, `rgba(236, 72, 153, ${0.05 - i * 0.01})`)
        ctx.fillStyle = waveGradient
        ctx.fill()
      }

      // Draw floating orb
      const orbX = width * 0.85
      const orbY = height * 0.75
      const orbRadius = 120

      // Outer glow
      const outerGlow = ctx.createRadialGradient(orbX, orbY, 0, orbX, orbY, orbRadius * 1.5)
      outerGlow.addColorStop(0, 'rgba(139, 92, 246, 0.3)')
      outerGlow.addColorStop(1, 'rgba(139, 92, 246, 0)')
      ctx.fillStyle = outerGlow
      ctx.fillRect(0, 0, width, height)

      // Main orb
      const orbGradient = ctx.createRadialGradient(orbX, orbY, 0, orbX, orbY, orbRadius)
      orbGradient.addColorStop(0, 'rgba(255, 255, 255, 0.3)')
      orbGradient.addColorStop(0.3, 'rgba(139, 92, 246, 0.5)')
      orbGradient.addColorStop(0.6, 'rgba(236, 72, 153, 0.4)')
      orbGradient.addColorStop(1, 'rgba(6, 182, 212, 0)')

      ctx.beginPath()
      ctx.arc(orbX, orbY, orbRadius, 0, Math.PI * 2)
      ctx.fillStyle = orbGradient
      ctx.fill()

      // Orb border
      ctx.strokeStyle = 'rgba(255, 255, 255, 0.4)'
      ctx.lineWidth = 2
      ctx.stroke()

      // Inner highlight
      const highlight = ctx.createRadialGradient(
        orbX - orbRadius * 0.3,
        orbY - orbRadius * 0.3,
        0,
        orbX,
        orbY,
        orbRadius * 0.5
      )
      highlight.addColorStop(0, 'rgba(255, 255, 255, 0.6)')
      highlight.addColorStop(1, 'rgba(255, 255, 255, 0)')
      ctx.fillStyle = highlight
      ctx.fillRect(0, 0, width, height)

      // Draw glow spots
      const glowSpots = [
        { x: width * 0.2, y: height * 0.3, color: '#8b5cf6' },
        { x: width * 0.8, y: height * 0.4, color: '#ec4899' },
        { x: width * 0.5, y: height * 0.7, color: '#06b6d4' }
      ]

      glowSpots.forEach(spot => {
        const glow = ctx.createRadialGradient(spot.x, spot.y, 0, spot.x, spot.y, 200)
        glow.addColorStop(0, spot.color + '40')
        glow.addColorStop(1, spot.color + '00')
        ctx.fillStyle = glow
        ctx.fillRect(0, 0, width, height)
      })

      animationId = requestAnimationFrame(draw)
    }

    resize()
    draw()

    window.addEventListener('resize', resize)

    return () => {
      cancelAnimationFrame(animationId)
      window.removeEventListener('resize', resize)
    }
  }, [])

  return <canvas ref={canvasRef} className="animated-bg" />
}

export default AnimatedBackground