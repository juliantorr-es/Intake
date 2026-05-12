/**
 * Quote intake form utilities.
 * Handles the multi-step quote intake process.
 */

import { createElement, setTextContent, replaceContent, clearElement } from './safe-dom.js';

/**
 * Service lanes for quotes.
 */
export const SERVICE_LANES = [
    { id: 'software_systems', name: 'Software Systems', description: 'Custom software development' },
    { id: 'photography', name: 'Photography', description: 'Photography services' },
    { id: 'practical_help', name: 'Practical Help', description: 'Hands-on assistance' },
    { id: 'unsure', name: 'Not Sure', description: 'Help me figure out what I need' }
];

/**
 * Quote intake form state.
 */
class IntakeFormState {
    constructor() {
        this.quoteId = null;
        this.serviceLane = null;
        this.shortSummary = '';
        this.detailedDescription = '';
        this.preferredTimeline = '';
        this.generalServiceArea = '';
        this.exactLocation = '';
        this.accessNotes = '';
        this.questionnaire = {};
        this.uploads = [];
        this.currentStep = 'service-lane';
    }
}

/**
 * Global state instance.
 */
const state = new IntakeFormState();

/**
 * Step definitions for the intake form.
 */
const STEPS = [
    { id: 'service-lane', name: 'Service', icon: '✓' },
    { id: 'details', name: 'Details', icon: '✓' },
    { id: 'location', name: 'Location', icon: '✓' },
    { id: 'access', name: 'Access', icon: '✓' },
    { id: 'uploads', name: 'Uploads', icon: '✓' },
    { id: 'submit', name: 'Submit', icon: '✓' }
];

/**
 * Create the intake form UI.
 * @param {Object} config - Configuration options
 * @returns {HTMLElement} The intake form element
 */
export function createIntakeForm(config = {}) {
    const container = createElement('div', { class: 'intake-form' });
    
    // Progress steps
    const progress = createProgressSteps();
    
    // Form container
    const formContainer = createElement('div', { class: 'intake-form-container' });
    
    // Current step content
    const stepContent = createElement('div', { class: 'intake-step-content' });
    
    replaceContent(formContainer, stepContent);
    replaceContent(container, progress, formContainer);
    
    // Render initial step
    renderStep('service-lane', stepContent, { onNext: () => goToStep('details') });
    
    function goToStep(stepId) {
        state.currentStep = stepId;
        renderStep(stepId, stepContent, {
            onNext: (nextStep) => goToStep(nextStep || nextStepId()),
            onBack: () => goToStep(previousStepId()),
            onComplete: () => {
                if (config.onComplete) {
                    config.onComplete(state);
                }
            }
        });
        updateProgress();
    }
    
    function nextStepId() {
        const currentIndex = STEPS.findIndex(s => s.id === state.currentStep);
        return STEPS[Math.min(currentIndex + 1, STEPS.length - 1)].id;
    }
    
    function previousStepId() {
        const currentIndex = STEPS.findIndex(s => s.id === state.currentStep);
        return STEPS[Math.max(currentIndex - 1, 0)].id;
    }
    
    function updateProgress() {
        // Update progress UI
        const progressEl = container.querySelector('.progress-steps');
        if (progressEl) {
            const steps = progressEl.querySelectorAll('.progress-step');
            const currentIndex = STEPS.findIndex(s => s.id === state.currentStep);
            
            steps.forEach((stepEl, index) => {
                const circle = stepEl.querySelector('.progress-step-circle');
                const label = stepEl.querySelector('.progress-step-label');
                const line = stepEl.querySelector('.progress-step-line');
                
                if (index <= currentIndex) {
                    circle.classList.add('completed');
                    circle.classList.remove('active');
                    label.classList.add('completed');
                    if (line) line.classList.add('active');
                } else if (index === currentIndex + 1 && currentIndex < STEPS.length - 1) {
                    circle.classList.add('active');
                    circle.classList.remove('completed');
                    label.classList.add('active');
                } else {
                    circle.classList.remove('active', 'completed');
                    label.classList.remove('active', 'completed');
                    if (line) line.classList.remove('active');
                }
            });
        }
    }
    
    return container;
}

/**
 * Create progress steps UI.
 * @returns {HTMLElement} The progress steps element
 */
function createProgressSteps() {
    const container = createElement('div', { class: 'progress-steps' });
    
    STEPS.forEach((step, index) => {
        const stepEl = createElement('div', { class: 'progress-step' });
        
        const circle = createElement('div', { class: 'progress-step-circle' }, step.icon);
        const label = createElement('span', { class: 'progress-step-label' }, step.name);
        
        replaceContent(stepEl, circle, label);
        
        if (index < STEPS.length - 1) {
            const line = createElement('div', { class: 'progress-step-line' });
            stepEl.appendChild(line);
        }
        
        container.appendChild(stepEl);
    });
    
    return container;
}

/**
 * Render a specific step.
 * @param {string} stepId - The step ID to render
 * @param {HTMLElement} container - The container to render into
 * @param {Object} handlers - Event handlers
 */
function renderStep(stepId, container, handlers) {
    clearElement(container);
    
    switch (stepId) {
        case 'service-lane':
            renderServiceLaneStep(container, handlers);
            break;
        case 'details':
            renderDetailsStep(container, handlers);
            break;
        case 'location':
            renderLocationStep(container, handlers);
            break;
        case 'access':
            renderAccessStep(container, handlers);
            break;
        case 'uploads':
            renderUploadsStep(container, handlers);
            break;
        case 'submit':
            renderSubmitStep(container, handlers);
            break;
        default:
            renderUnknownStep(container);
    }
}

/**
 * Render the service lane selection step.
 */
function renderServiceLaneStep(container, handlers) {
    const title = createElement('h2', {}, 'What service do you need?');
    const description = createElement('p', { class: 'text-muted' },
        'Select the service lane that best describes your needs.'
    );
    
    const laneSelector = createElement('div', { class: 'service-lane-selector' });
    
    SERVICE_LANES.forEach(lane => {
        const button = createElement('button', {
            class: 'service-lane-btn' + (state.serviceLane === lane.id ? ' selected' : ''),
            'data-lane': lane.id
        }, lane.name);
        
        button.addEventListener('click', () => {
            state.serviceLane = lane.id;
            // Update all buttons
            laneSelector.querySelectorAll('.service-lane-btn').forEach(btn => {
                btn.classList.toggle('selected', btn.dataset.lane === lane.id);
            });
        });
        
        laneSelector.appendChild(button);
    });
    
    const nextBtn = createElement('button', {
        class: 'btn btn-primary mt-md',
        disabled: !state.serviceLane
    }, 'Next: Details');
    
    nextBtn.addEventListener('click', () => {
        if (state.serviceLane && handlers.onNext) {
            // Start a new quote
            startQuote();
        }
    });
    
    replaceContent(container, title, description, laneSelector, nextBtn);
    
    // Enable/disable next button when selection changes
    laneSelector.addEventListener('click', () => {
        nextBtn.disabled = !state.serviceLane;
    });
}

/**
 * Start a new quote via API.
 */
async function startQuote() {
    try {
        const response = await fetch('/api/quotes/start', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ service_lane: state.serviceLane })
        });
        
        const data = await response.json();
        state.quoteId = data.quote_id;
        
        // Proceed to next step
        if (handlers.onNext) {
            handlers.onNext('details');
        }
    } catch (error) {
        console.error('Failed to start quote:', error);
        // Show error and re-enable
    }
}

/**
 * Render the details step.
 */
function renderDetailsStep(container, handlers) {
    const title = createElement('h2', {}, 'Tell us about your project');
    const description = createElement('p', { class: 'text-muted' },
        'Provide some details to help us understand your needs.'
    );
    
    const form = createElement('form', {});
    
    const summaryGroup = createElement('div', { class: 'form-group' });
    const summaryLabel = createElement('label', { class: 'form-label' }, 'Brief Summary');
    const summaryInput = createElement('input', {
        type: 'text',
        class: 'form-input',
        placeholder: 'e.g., Need a website for my business',
        value: state.shortSummary
    });
    summaryInput.addEventListener('input', () => {
        state.shortSummary = summaryInput.value;
    });
    replaceContent(summaryGroup, summaryLabel, summaryInput);
    
    const descriptionGroup = createElement('div', { class: 'form-group' });
    const descriptionLabel = createElement('label', { class: 'form-label' }, 'Description');
    const descriptionInput = createElement('textarea', {
        class: 'form-textarea',
        placeholder: 'Describe your needs in detail...',
        value: state.detailedDescription
    });
    descriptionInput.addEventListener('input', () => {
        state.detailedDescription = descriptionInput.value;
    });
    replaceContent(descriptionGroup, descriptionLabel, descriptionInput);
    
    const timelineGroup = createElement('div', { class: 'form-group' });
    const timelineLabel = createElement('label', { class: 'form-label' }, 'Preferred Timeline');
    const timelineInput = createElement('input', {
        type: 'text',
        class: 'form-input',
        placeholder: 'e.g., Within 2 weeks, ASAP, etc.',
        value: state.preferredTimeline
    });
    timelineInput.addEventListener('input', () => {
        state.preferredTimeline = timelineInput.value;
    });
    replaceContent(timelineGroup, timelineLabel, timelineInput);
    
    const nav = createElement('div', { class: 'form-navigation gap-md mt-md' });
    const backBtn = createElement('button', { class: 'btn btn-secondary' }, 'Back');
    const nextBtn = createElement('button', { class: 'btn btn-primary' }, 'Next: Location');
    
    backBtn.addEventListener('click', () => handlers.onBack && handlers.onBack());
    nextBtn.addEventListener('click', async () => {
        // Save details
        await saveQuoteDetails();
        handlers.onNext && handlers.onNext('location');
    });
    
    replaceContent(nav, backBtn, nextBtn);
    replaceContent(form, summaryGroup, descriptionGroup, timelineGroup, nav);
    replaceContent(container, title, description, form);
}

/**
 * Save quote details via API.
 */
async function saveQuoteDetails() {
    if (!state.quoteId) return;
    
    try {
        await fetch(`/api/quotes/${state.quoteId}/answers`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                short_summary: state.shortSummary,
                detailed_description: state.detailedDescription,
                preferred_timeline: state.preferredTimeline
            })
        });
    } catch (error) {
        console.error('Failed to save quote details:', error);
    }
}

/**
 * Render the location step.
 */
function renderLocationStep(container, handlers) {
    const title = createElement('h2', {}, 'Where do you need service?');
    const description = createElement('p', { class: 'text-muted' },
        'Provide your location information.'
    );
    
    const form = createElement('form', {});
    
    const generalGroup = createElement('div', { class: 'form-group' });
    const generalLabel = createElement('label', { class: 'form-label' }, 'General Service Area');
    const generalInput = createElement('input', {
        type: 'text',
        class: 'form-input',
        placeholder: 'e.g., San Francisco Bay Area, Remote, etc.',
        value: state.generalServiceArea
    });
    generalInput.addEventListener('input', () => {
        state.generalServiceArea = generalInput.value;
    });
    replaceContent(generalGroup, generalLabel, generalInput);
    
    const exactGroup = createElement('div', { class: 'form-group' });
    const exactLabel = createElement('label', { class: 'form-label' }, 'Exact Address (Optional)');
    const exactInput = createElement('textarea', {
        class: 'form-textarea',
        placeholder: 'Exact address for on-site work (will be encrypted)',
        value: state.exactLocation
    });
    exactInput.addEventListener('input', () => {
        state.exactLocation = exactInput.value;
    });
    replaceContent(exactGroup, exactLabel, exactInput);
    
    const info = createElement('p', { class: 'text-muted', style: 'font-size: 0.875rem;' },
        'Exact location is encrypted and only accessible to authorized operators.'
    );
    
    const nav = createElement('div', { class: 'form-navigation gap-md mt-md' });
    const backBtn = createElement('button', { class: 'btn btn-secondary' }, 'Back');
    const nextBtn = createElement('button', { class: 'btn btn-primary' }, 'Next: Access');
    
    backBtn.addEventListener('click', () => handlers.onBack && handlers.onBack());
    nextBtn.addEventListener('click', async () => {
        await saveQuoteLocation();
        handlers.onNext && handlers.onNext('access');
    });
    
    replaceContent(nav, backBtn, nextBtn);
    replaceContent(form, generalGroup, exactGroup, info, nav);
    replaceContent(container, title, description, form);
}

/**
 * Save quote location via API.
 */
async function saveQuoteLocation() {
    if (!state.quoteId) return;
    
    try {
        await fetch(`/api/quotes/${state.quoteId}/location`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                general_service_area: state.generalServiceArea,
                encrypted_exact_location: null // Encryption handled server-side
            })
        });
    } catch (error) {
        console.error('Failed to save quote location:', error);
    }
}

/**
 * Render the access step.
 */
function renderAccessStep(container, handlers) {
    const title = createElement('h2', {}, 'Access Information');
    const description = createElement('p', { class: 'text-muted' },
        'Any special access instructions, gates, codes, etc.'
    );
    
    const form = createElement('form', {});
    
    const accessGroup = createElement('div', { class: 'form-group' });
    const accessLabel = createElement('label', { class: 'form-label' }, 'Access Notes (Optional)');
    const accessInput = createElement('textarea', {
        class: 'form-textarea',
        placeholder: 'e.g., Gate code, parking instructions, security requirements',
        value: state.accessNotes
    });
    accessInput.addEventListener('input', () => {
        state.accessNotes = accessInput.value;
    });
    replaceContent(accessGroup, accessLabel, accessInput);
    
    const info = createElement('p', { class: 'text-muted', style: 'font-size: 0.875rem;' },
        'Access notes are encrypted and only accessible to authorized operators.'
    );
    
    const nav = createElement('div', { class: 'form-navigation gap-md mt-md' });
    const backBtn = createElement('button', { class: 'btn btn-secondary' }, 'Back');
    const nextBtn = createElement('button', { class: 'btn btn-primary' }, 'Next: Uploads');
    
    backBtn.addEventListener('click', () => handlers.onBack && handlers.onBack());
    nextBtn.addEventListener('click', () => {
        handlers.onNext && handlers.onNext('uploads');
    });
    
    replaceContent(nav, backBtn, nextBtn);
    replaceContent(form, accessGroup, info, nav);
    replaceContent(container, title, description, form);
}

/**
 * Render the uploads step.
 */
function renderUploadsStep(container, handlers) {
    const title = createElement('h2', {}, 'Upload Files');
    const description = createElement('p', { class: 'text-muted' },
        'Upload any relevant files (photos, documents, etc.).'
    );
    
    const uploadList = createElement('div', { class: 'upload-list-container' });
    const uploadListEl = createElement('ul', { class: 'upload-list' });
    uploadList.appendChild(uploadListEl);
    
    const dropZone = createElement('div', {
        class: 'upload-dropzone',
        style: 'border: 2px dashed #ccc; border-radius: 8px; padding: 40px; text-align: center; margin-bottom: 20px;'
    }, 'Drag & drop files here or click to browse');
    
    // Update upload list
    function updateUploadList() {
        clearElement(uploadListEl);
        state.uploads.forEach(upload => {
            const item = createElement('li', { class: 'upload-item' });
            const info = createElement('div', { class: 'upload-item-info' });
            const name = createElement('div', { class: 'upload-item-name' }, upload.name);
            const meta = createElement('div', { class: 'upload-item-meta' },
                `${upload.type}, ${formatFileSize(upload.size)}`);
            replaceContent(info, name, meta);
            replaceContent(item, info);
            uploadListEl.appendChild(item);
        });
    }
    
    dropZone.addEventListener('click', () => {
        // Open file dialog
        const input = document.createElement('input');
        input.type = 'file';
        input.multiple = true;
        input.addEventListener('change', async (e) => {
            await handleFiles(e.target.files);
        });
        input.click();
    });
    
    async function handleFiles(files) {
        for (const file of Array.from(files)) {
            // Declare upload
            try {
                const response = await fetch(`/api/quotes/${state.quoteId}/uploads/declare`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        original_filename: file.name,
                        content_type: file.type || 'application/octet-stream',
                        size_bytes: file.size,
                        purpose: ''
                    })
                });
                
                const data = await response.json();
                state.uploads.push({
                    upload_id: data.upload_id,
                    name: file.name,
                    type: file.type || 'application/octet-stream',
                    size: file.size
                });
            } catch (error) {
                console.error('Failed to declare upload:', error);
            }
        }
        updateUploadList();
    }
    
    const nav = createElement('div', { class: 'form-navigation gap-md mt-md' });
    const backBtn = createElement('button', { class: 'btn btn-secondary' }, 'Back');
    const nextBtn = createElement('button', { class: 'btn btn-primary' }, 'Next: Review & Submit');
    
    backBtn.addEventListener('click', () => handlers.onBack && handlers.onBack());
    nextBtn.addEventListener('click', () => {
        handlers.onNext && handlers.onNext('submit');
    });
    
    replaceContent(nav, backBtn, nextBtn);
    replaceContent(container, title, description, uploadList, dropZone, nav);
}

/**
 * Format file size for display.
 */
function formatFileSize(bytes) {
    if (bytes < 1024) return bytes + ' B';
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + ' KB';
    return (bytes / (1024 * 1024)).toFixed(1) + ' MB';
}

/**
 * Render the submit step.
 */
function renderSubmitStep(container, handlers) {
    const title = createElement('h2', {}, 'Review & Submit');
    const description = createElement('p', { class: 'text-muted' },
        'Review your information and submit your quote request.'
    );
    
    const summary = createElement('div', { class: 'intake-summary gap-md' });
    
    const serviceLane = createElement('div', { class: 'summary-item' });
    const serviceLaneLabel = createElement('strong', {}, 'Service Lane: ');
    const serviceLaneValue = createElement('span', {});
    setTextContent(serviceLaneValue, 
        SERVICE_LANES.find(l => l.id === state.serviceLane)?.name || state.serviceLane);
    replaceContent(serviceLane, serviceLaneLabel, serviceLaneValue);
    
    const summaryEl = createElement('div', { class: 'summary-item' });
    const summaryLabel = createElement('strong', {}, 'Summary: ');
    const summaryValue = createElement('span', {}, state.shortSummary || '(not provided)');
    replaceContent(summaryEl, summaryLabel, summaryValue);
    
    const locationEl = createElement('div', { class: 'summary-item' });
    const locationLabel = createElement('strong', {}, 'Location: ');
    const locationValue = createElement('span', {}, state.generalServiceArea || '(not provided)');
    replaceContent(locationEl, locationLabel, locationValue);
    
    const timelineEl = createElement('div', { class: 'summary-item' });
    const timelineLabel = createElement('strong', {}, 'Timeline: ');
    const timelineValue = createElement('span', {}, state.preferredTimeline || '(not specified)');
    replaceContent(timelineEl, timelineLabel, timelineValue);
    
    if (state.uploads.length > 0) {
        const uploadsEl = createElement('div', { class: 'summary-item' });
        const uploadsLabel = createElement('strong', {}, 'Uploads: ');
        const uploadsList = createElement('span', {}, 
            state.uploads.map(u => u.name).join(', ') + ` (${state.uploads.length})`);
        replaceContent(uploadsEl, uploadsLabel, uploadsList);
        summary.appendChild(uploadsEl);
    }
    
    replaceContent(summary, serviceLane, summaryEl, locationEl, timelineEl);
    
    const submitBtn = createElement('button', { class: 'btn btn-primary mt-md' }, 
        'Submit Quote Request');
    
    submitBtn.addEventListener('click', async () => {
        try {
            const response = await fetch(`/api/quotes/${state.quoteId}/submit`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' }
            });
            
            const data = await response.json();
            
            if (data.success) {
                // Show success
                clearElement(container);
                const success = createElement('div', { class: 'intake-success text-center gap-md' });
                const successIcon = createElement('div', { style: 'font-size: 48px;' }, '✓');
                const successTitle = createElement('h2', {}, 'Quote Submitted!');
                const successMessage = createElement('p', { class: 'text-muted' },
                    'Your quote request has been submitted. We will review and get back to you shortly.');
                
                if (data.quote_id) {
                    const quoteIdEl = createElement('p', { class: 'text-muted' },
                        `Reference ID: ${data.quote_id}`);
                    replaceContent(success, successIcon, successTitle, successMessage, quoteIdEl);
                } else {
                    replaceContent(success, successIcon, successTitle, successMessage);
                }
                
                container.appendChild(success);
                
                if (handlers.onComplete) {
                    handlers.onComplete();
                }
            }
        } catch (error) {
            console.error('Failed to submit quote:', error);
            const errorEl = createElement('div', { 
                class: 'alert alert-danger mt-md',
                style: 'color: #991b1b; background-color: #fee2e2; padding: 10px; border-radius: 4px;'
            }, `Submission failed: ${error.message}`);
            container.appendChild(errorEl);
        }
    });
    
    const nav = createElement('div', { class: 'form-navigation gap-md mt-md' });
    const backBtn = createElement('button', { class: 'btn btn-secondary' }, 'Back');
    replaceContent(nav, backBtn, submitBtn);
    
    backBtn.addEventListener('click', () => handlers.onBack && handlers.onBack());
    
    replaceContent(container, title, description, summary, nav);
}

/**
 * Render an unknown step.
 */
function renderUnknownStep(container) {
    replaceContent(container, 
        createElement('h2', {}, 'Unknown Step'),
        createElement('p', {}, 'This step does not exist.')
    );
}

/**
 * Start the intake form.
 * @param {Object} config - Configuration options
 * @returns {HTMLElement} The form element
 */
export function startIntakeForm(config = {}) {
    return createIntakeForm(config);
}
