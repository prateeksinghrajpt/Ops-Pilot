import { useState } from 'react'
import { Activity, ArrowRight, LoaderCircle, ShieldCheck } from 'lucide-react'
import { api, setAccessToken } from './api'

export default function AuthScreen({ onAuthenticated }) {
  const [mode, setMode] = useState('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const submit = async (event) => {
    event.preventDefault()
    if (mode === 'signup' && password !== confirmPassword) {
      setError('Passwords do not match.')
      return
    }
    setBusy(true)
    setError('')
    try {
      const result = mode === 'signup'
        ? await api.signup({ email, password })
        : await api.login({ email, password })
      setAccessToken(result.access_token)
      onAuthenticated(result.user)
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return <main className="auth-shell">
    <section className="auth-panel">
      <div className="auth-brand"><div className="brand-mark"><Activity size={22}/></div><div><b>OpsPilot</b><span>AI INCIDENT RCA</span></div></div>
      <div className="auth-copy"><div className="eyebrow"><span className="pulse"/> SECURE WORKSPACE</div><h1>{mode === 'login' ? 'Welcome back' : 'Create your workspace'}</h1><p>{mode === 'login' ? 'Sign in to investigate your incidents and evidence.' : 'Create an account to start your private incident RCA workspace.'}</p></div>
      <form className="auth-form" onSubmit={submit}>
        <label>Email address<input type="email" value={email} onChange={event => setEmail(event.target.value)} autoComplete="email" required placeholder="engineer@example.com"/></label>
        <label>Password<input type="password" value={password} onChange={event => setPassword(event.target.value)} autoComplete={mode === 'login' ? 'current-password' : 'new-password'} minLength="12" required placeholder="At least 12 characters"/></label>
        {mode === 'signup' && <label>Confirm password<input type="password" value={confirmPassword} onChange={event => setConfirmPassword(event.target.value)} autoComplete="new-password" minLength="12" required placeholder="Repeat your password"/></label>}
        {error && <div className="auth-error">{error}</div>}
        <button className="primary-btn auth-submit" disabled={busy}>{busy ? <LoaderCircle className="spin" size={16}/> : <ArrowRight size={16}/>} {mode === 'login' ? 'Sign in' : 'Create account'}</button>
      </form>
      <button className="auth-switch" type="button" onClick={() => { setMode(mode === 'login' ? 'signup' : 'login'); setError('') }}>{mode === 'login' ? 'Need an account? Create one' : 'Already have an account? Sign in'}</button>
      <div className="auth-note"><ShieldCheck size={15}/> Your incidents and RCA reports are private to your account.</div>
    </section>
  </main>
}
