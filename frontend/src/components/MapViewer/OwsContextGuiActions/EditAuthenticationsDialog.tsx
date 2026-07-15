import { ReactNode, useMemo, useState } from 'react';

import AddIcon from '@mui/icons-material/Add';
import ClearIcon from '@mui/icons-material/Clear';
import DeleteIcon from '@mui/icons-material/Delete';
import EditIcon from '@mui/icons-material/Edit';
import { Box, Divider, IconButton, List, ListItem, ListItemText, TextField, Typography } from '@mui/material';
import Button from '@mui/material/Button';
import Dialog from '@mui/material/Dialog';
import DialogActions from '@mui/material/DialogActions';
import DialogContent from '@mui/material/DialogContent';
import DialogTitle from '@mui/material/DialogTitle';

import { useOwsContextBase } from '../../../react-ows-lib/ContextProvider/OwsContextBase';

export interface EditAuthenticationsDialogProps {
    open: boolean
    setOpen: (open: boolean) => void
}


const EditAuthenticationsDialog = ({open, setOpen}: EditAuthenticationsDialogProps): ReactNode => {
  const { owsContext, updateOwsContext } = useOwsContextBase() 
  const authentications = useMemo(()=> owsContext.authentications ?? [], [owsContext])
  
  const [localAuthentications, setLocalAuthentications] = useState(authentications)
  const [editingIndex, setEditingIndex] = useState<number | null>(null)
  

  const handleOpenDialog = () => {
    setLocalAuthentications(authentications)
    setEditingIndex(null)
    resetForm()
  }

  const handleCloseDialog = () => {
    setOpen(false)
  }

  const resetForm = () => {
    setFormData({
      getCapabilitiesUrl: '',
      username: '',
      password: ''
    })
  }

  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const { name, value } = e.target
    setFormData(prev => ({
      ...prev,
      [name]: value
    }))
  }

  const handleAddAuthentication = () => {
    if (!formData.getCapabilitiesUrl.trim()) {
      return
    }
    
    if (editingIndex !== null) {
      const updated = [...localAuthentications]
      updated[editingIndex] = formData
      setLocalAuthentications(updated)
      setEditingIndex(null)
    } else {
      setLocalAuthentications([...localAuthentications, formData])
    }
    resetForm()
  }

  const handleEditAuthentication = (index: number) => {
    setFormData(localAuthentications[index])
    setEditingIndex(index)
  }

  const handleDeleteAuthentication = (index: number) => {
    setLocalAuthentications(localAuthentications.filter((_, i) => i !== index))
    if (editingIndex === index) {
      setEditingIndex(null)
      resetForm()
    }
  }

  const handleCancelEdit = () => {
    setEditingIndex(null)
    resetForm()
  }

  const handleSave = (e: React.FormEvent) => {
    e.preventDefault()
    if (updateOwsContext) {
      updateOwsContext({
        ...owsContext,
        authentications: localAuthentications
      })
    }
    handleCloseDialog()
  }

  return (
      <Dialog
        open={open}
        onClose={handleCloseDialog}
        maxWidth="md"
        fullWidth
      >
        <DialogTitle>Edit Authentications</DialogTitle>
        <DialogContent>
          <Box component="form" onSubmit={handleSave} sx={{ display: 'flex', flexDirection: 'column', gap: 2 }}>
            
            {/* Existing Authentications List */}
            {localAuthentications.length > 0 && (
              <Box>
                <Typography variant="subtitle2" sx={{ mb: 1, fontWeight: 'bold' }}>
                  Existing Authentications:
                </Typography>
                <List sx={{ border: '1px solid #ddd', borderRadius: 1, maxHeight: 250, overflow: 'auto' }}>
                  {localAuthentications.map((auth, index) => (
                    <div key={index}>
                      <ListItem
                        secondaryAction={
                          <Box>
                            <IconButton
                              edge="end"
                              onClick={() => handleEditAuthentication(index)}
                              size="small"
                              title="Edit"
                            >
                              <EditIcon />
                            </IconButton>
                            <IconButton
                              edge="end"
                              onClick={() => handleDeleteAuthentication(index)}
                              size="small"
                              title="Delete"
                            >
                              <DeleteIcon />
                            </IconButton>
                          </Box>
                        }
                      >
                        <ListItemText
                          primary={auth.getCapabilitiesUrl}
                          secondary={auth.username ? `Username: ${auth.username}` : 'No username'}
                        />
                      </ListItem>
                      {index < localAuthentications.length - 1 && <Divider />}
                    </div>
                  ))}
                </List>
              </Box>
            )}

            {/* Form to add/edit authentication */}
            <Box sx={{ p: 2, backgroundColor: '#f5f5f5', borderRadius: 1 }}>
              <Typography variant="subtitle2" sx={{ mb: 2, fontWeight: 'bold' }}>
                {editingIndex !== null ? 'Edit Authentication' : 'Add New Authentication'}
              </Typography>
              
              <TextField
                autoFocus
                required
                margin="dense"
                id="getCapabilitiesUrl"
                name="getCapabilitiesUrl"
                label="Get Capabilities URL"
                type="url"
                fullWidth
                variant="outlined"
                value={formData.getCapabilitiesUrl}
                onChange={handleInputChange}
                size="small"
              />
              <TextField
                margin="dense"
                id="username"
                name="username"
                label="Username (optional)"
                fullWidth
                variant="outlined"
                value={formData.username}
                onChange={handleInputChange}
                size="small"
              />
              <TextField
                margin="dense"
                id="password"
                name="password"
                label="Password (optional)"
                type="password"
                fullWidth
                variant="outlined"
                value={formData.password}
                onChange={handleInputChange}
                size="small"
              />

              <Box sx={{ display: 'flex', gap: 1, mt: 2 }}>
                <Button
                  variant="contained"
                  color="primary"
                  onClick={handleAddAuthentication}
                  startIcon={editingIndex !== null ? <EditIcon /> : <AddIcon />}
                  size="small"
                >
                  {editingIndex !== null ? 'Update' : 'Add'}
                </Button>
                {editingIndex !== null && (
                  <Button
                    variant="outlined"
                    onClick={handleCancelEdit}
                    startIcon={<ClearIcon />}
                    size="small"
                  >
                    Cancel
                  </Button>
                )}
              </Box>
            </Box>
          </Box>
        </DialogContent>
        <DialogActions>
          <Button onClick={handleCloseDialog}>Cancel</Button>
          <Button onClick={handleSave} color="primary" variant="contained">
            Save Changes
          </Button>
        </DialogActions>
      </Dialog>
  );
}

export default EditAuthenticationsDialog;