import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { Button, Card, Chip, PageTitle } from '../../components/ui'
import {
  acceptGuardianLink,
  changePassword,
  getCurrentUser,
  listGuardianLinks,
  requestGuardianLink,
  revokeGuardianLink,
  type AuthUser,
  type GuardianLink,
} from '../../services/auth'

export function ProfilePage() {
  const [user, setUser] = useState<AuthUser | null>(null)
  const [links, setLinks] = useState<GuardianLink[]>([])
  const [studentEmail, setStudentEmail] = useState('')
  const [error, setError] = useState('')
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const navigate = useNavigate()

  const load = async () => {
    try {
      const [currentUser, currentLinks] = await Promise.all([
        getCurrentUser(),
        listGuardianLinks(),
      ])
      setUser(currentUser)
      setLinks(currentLinks)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '账号信息读取失败')
    }
  }

  useEffect(() => { void load() }, [])

  const createLink = async () => {
    setError('')
    try {
      await requestGuardianLink(studentEmail, 'guardian')
      setStudentEmail('')
      await load()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '关联申请提交失败')
    }
  }

  const updateLink = async (operation: () => Promise<unknown>) => {
    setError('')
    try {
      await operation()
      await load()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '关联状态更新失败')
    }
  }

  const updatePassword = async () => {
    setError('')
    try {
      await changePassword(currentPassword, newPassword)
      navigate('/auth', { replace: true })
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '密码修改失败')
    }
  }

  return <div className="page narrow">
    <PageTitle eyebrow="个人空间" title="账号与学习设置" description="学习数据只向你确认过的账号开放。" />
    <Card><div className="profile-row"><span className="avatar profile-avatar">{user?.display_name.slice(0, 1) ?? '我'}</span><div><strong>{user?.display_name ?? '正在读取…'}</strong><p>{user?.email}</p></div></div></Card>
    {user?.role === 'student' && <Card><h3>家长授权</h3><p>家长发起申请后，需要你确认才能查看学习记录。</p>
      {links.filter(link => link.status !== 'revoked').map(link => <div className="profile-link-row" key={link.id}><div><strong>{link.guardian_name}</strong><p>{link.status === 'pending' ? '等待你确认' : '已授权'}</p></div><div className="chip-row">{link.status === 'pending' && <Button onClick={() => void updateLink(() => acceptGuardianLink(link.id))}>确认</Button>}<Button secondary onClick={() => void updateLink(() => revokeGuardianLink(link.id))}>解除</Button></div></div>)}
    </Card>}
    {user?.role === 'guardian' && <Card><h3>关联学生</h3><p>输入学生注册邮箱；学生确认后你才能读取学习数据。</p><label className="field-label" htmlFor="student-email">学生邮箱</label><input className="text-input" id="student-email" type="email" value={studentEmail} onChange={event => setStudentEmail(event.target.value)} /><div className="form-foot"><span className="tiny-muted">当前关联：{links.filter(link => link.status === 'active').length} 个</span><Button onClick={() => void createLink()}>发送申请</Button></div>
      {links.filter(link => link.status !== 'revoked').map(link => <div className="profile-link-row" key={link.id}><div><strong>{link.student_name}</strong><p>{link.status === 'active' ? '已获得授权' : '等待学生确认'}</p></div><Button secondary onClick={() => void updateLink(() => revokeGuardianLink(link.id))}>解除</Button></div>)}
    </Card>}
    <Card><h3>修改密码</h3><p>修改后其他设备和当前登录状态都会失效，需要重新登录。</p><label className="field-label" htmlFor="current-password">当前密码</label><input className="text-input" id="current-password" type="password" autoComplete="current-password" value={currentPassword} onChange={event => setCurrentPassword(event.target.value)} /><label className="field-label" htmlFor="new-password">新密码</label><input className="text-input" id="new-password" type="password" minLength={8} maxLength={128} autoComplete="new-password" value={newPassword} onChange={event => setNewPassword(event.target.value)} /><div className="form-foot"><span className="tiny-muted">至少 8 个字符</span><Button onClick={() => void updatePassword()}>更新密码</Button></div></Card>
    {error && <p className="form-error" role="alert">{error}</p>}
    {user?.role === 'student' && <Card><h3>关注的学习方向</h3><div className="chip-row"><Chip tone="green">一元一次方程</Chip><Chip>整式运算</Chip><Chip>函数基础</Chip></div></Card>}
  </div>
}
